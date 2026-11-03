#!/usr/bin/env python3
"""
precommit_policy.py — the pre-commit resolution policy (#75).

Every finding the pre-commit hook reports has exactly one resolution:

  fix-required       every correctness rule (invalid commit draft, broken
                     acknowledgement evidence, a legacy record, ...). Fix
                     and retry; nothing approves it.
  warning            a HIGH/CRITICAL dangerous pattern under the default
                     policy. It is never approvable and never reaches the
                     override envelope.
  pause              the commit-level `dangerous-pattern-pause` rule: while
                     any warning finding has no recorded decision, the
                     commit pauses so the agent asks the Architect. A
                     recorded acknowledgement (the Architect's decision) or
                     a recorded skip (the agent proceeds without one,
                     shown in Git) clears it. No approval command.
  external-approval  the tree-bound approval envelope (precommit_override):
                     a missing charter update (the Architect may approve
                     the exact staged change when no charter edit is
                     warranted), and a HIGH/CRITICAL dangerous pattern
                     where the mode requires it (Enterprise
                     `evidence_only`).

The table is fixed and closed: there is no repository policy schema in
the first pass. Both gator-pre-commit.py copies (wheel template and
Enterprise bundled) call this module, so the rules live in one
byte-identical place.

Architect acknowledgement evidence (#75): when the Architect decides to keep
a `warning` finding, commit_draft.md names it in the flat frontmatter list
`dangerous-pattern-acknowledgements: [RULE@path:line, ...]` and explains it
in a `## Architect acknowledgement` body section. validate_acknowledgements()
binds that evidence to the current warning findings and fails closed;
acknowledgement_trailers() renders it. An acknowledgement is never an
override: it does not touch the precommit_override envelope.

@reads/@writes: nothing (pure functions)
@does-not-own: rule evaluation (gator-pre-commit.py), the override
               envelope (precommit_override.py), lint (precommit_lint.py)
"""

import re

import precommit_override as _override

FIX_REQUIRED = "fix-required"
WARNING = "warning"
EXTERNAL_APPROVAL = "external-approval"
PAUSE = "pause"
PAUSE_RULE = "dangerous-pattern-pause"

DANGEROUS_SEVERITIES = frozenset({"CRITICAL", "HIGH"})

# Effective hook mode -> resolution of a HIGH/CRITICAL dangerous finding.
# "warn" and "off" are the legacy broad modes; the hook handles them as
# before (warn moves every failure to warnings; off skips the checks).
_DANGEROUS_RESOLUTION = {
    "strict": WARNING,
    "warn": WARNING,
    "off": WARNING,
    "evidence_only": EXTERNAL_APPROVAL,
}


def dangerous_resolution(mode):
    """Resolution of a HIGH/CRITICAL dangerous finding in ``mode``.

    Unknown modes fall back to the strict default, as the hook's
    enforcement reader does.
    """
    return _DANGEROUS_RESOLUTION.get(mode, WARNING)


def split_lint(findings, mode):
    """Split Layer 1 findings into (dangerous, external, advisory).

    ``dangerous``: HIGH/CRITICAL findings whose resolution is ``warning``.
    ``external``:  HIGH/CRITICAL findings whose resolution is
                   ``external-approval``.
    ``advisory``:  MEDIUM/LOW findings (plain warnings in every mode).
    Each finding keeps its structured fields.
    """
    resolution = dangerous_resolution(mode)
    dangerous, external, advisory = [], [], []
    for finding in findings:
        if finding.get("severity") in DANGEROUS_SEVERITIES:
            (external if resolution == EXTERNAL_APPROVAL else dangerous).append(finding)
        else:
            advisory.append(finding)
    return dangerous, external, advisory


def resolution_map(external_findings):
    """The explicit map passed to the override envelope: only these rules
    are ``external-approval``; every other rule is ``fix-required``."""
    return {f["rule"]: EXTERNAL_APPROVAL for f in external_findings}


def charter_resolutions(failures):
    """``external-approval`` for the charter rules among ``failures``: a
    missing charter update blocks, and the Architect may approve the exact
    staged change when the charter check misfires or no charter edit is
    warranted."""
    return {rule: EXTERNAL_APPROVAL for rule, _ in failures
            if rule in _override.CHARTER_RULES}


def report_categories(failures, resolutions):
    """Split (rule, message) failures into (fix_required, external_approval)
    rule lists using the explicit map. A rule the map does not name is
    fix-required, so a correctness failure is never reported as approvable.
    The pause rule is in neither list: it is reported on its own."""
    resolutions = resolutions or {}
    fix_required, external = [], []
    for rule, _ in failures:
        res = resolutions.get(rule)
        if res == PAUSE:
            continue
        target = external if res == EXTERNAL_APPROVAL else fix_required
        if rule not in target:
            target.append(rule)
    return fix_required, external


def pause_failure(unresolved_keys):
    """The commit-level pause: (PAUSE_RULE, message), or None when every
    warning finding has a recorded decision."""
    if not unresolved_keys:
        return None
    return (PAUSE_RULE,
            "Dangerous pattern(s) without a recorded decision: "
            + ", ".join(unresolved_keys)
            + ". Ask the Architect about each one (fix, remove, or keep), then "
            f"record the decision in commit_draft.md ({ACK_FIELD} + the "
            f"`{ACK_HEADING}` section) and retry. To proceed without asking, "
            f"list the keys in {SKIP_FIELD}; the commit then records them as "
            "unacknowledged.")


# Path characters the flat frontmatter list, the body bullet or the
# comma-joined trailer cannot hold. They are percent-encoded, so every key
# fits all three unambiguously; other characters (including inner spaces)
# stay byte-for-byte.
_KEY_ESCAPES = {"%": "%25", ",": "%2C", "[": "%5B", "]": "%5D",
                '"': "%22", "'": "%27", "`": "%60"}


def _encode_key_path(path):
    out = "".join(
        _KEY_ESCAPES.get(c) or (c if " " <= c != "\x7f" else "%{:02X}".format(ord(c)))
        for c in path)
    core = out.strip(" ")
    if not core:
        return "%20" * len(out)
    lead = len(out) - len(out.lstrip(" "))
    trail = len(out) - len(out.rstrip(" "))
    # The flat list parser strips item ends, so edge spaces are encoded.
    return "%20" * lead + core + "%20" * trail


def finding_key(finding):
    """Stable, readable key ``RULE@path:line`` for a finding. The path uses
    forward slashes and is percent-encoded only where the flat list, the
    body bullet or the trailer could not hold it (``,`` -> ``%2C``, see
    ``_KEY_ESCAPES``; control characters; edge spaces). A dangerous filename
    finding has line 0. It never contains the matched source text."""
    path = _encode_key_path(str(finding["file"]).replace("\\", "/"))
    return f"{finding['rule']}@{path}:{int(finding['line'])}"


def finding_keys(findings):
    """Deduplicated keys in first-seen order."""
    keys = []
    for finding in findings:
        key = finding_key(finding)
        if key not in keys:
            keys.append(key)
    return keys


def finding_text(finding):
    """One-line ``file:line — message`` text for a finding (no matched text)."""
    return f"{finding['file']}:{finding['line']} — {finding['message']}"


# ---------------------------------------------------------------------------
# Architect acknowledgement evidence
# ---------------------------------------------------------------------------

ACK_FIELD = "dangerous-pattern-acknowledgements"
SKIP_FIELD = "dangerous-pattern-skips"
ACK_RULE = "invalid-dangerous-pattern-acknowledgement"
ACK_HEADING = "## Architect acknowledgement"
KEY_PATTERN = re.compile(r"^[A-Z]+-[0-9]+@.+:[0-9]+$")
_BULLET = re.compile(r"^- `([^`]+)`:\s*(.*)$")


def _ack_section(body):
    """(present, bullets) for the ``## Architect acknowledgement`` section.

    ``bullets`` is a list of (key, text); an indented continuation line
    extends the previous bullet's text. The section ends at the next
    level-1 or level-2 heading.
    """
    present, bullets, inside = False, [], False
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped == ACK_HEADING:
            present, inside = True, True
            continue
        if inside and (line.startswith("## ") or line.startswith("# ")):
            inside = False
        if not inside or not stripped:
            continue
        m = _BULLET.match(line)
        if m:
            bullets.append([m.group(1), m.group(2).strip()])
        elif bullets and line[:1] in (" ", "\t"):
            bullets[-1][1] = (bullets[-1][1] + " " + stripped).strip()
    return present, [tuple(b) for b in bullets]


def validate_acknowledgements(frontmatter, body, dangerous):
    """Bind draft acknowledgement evidence to the current warning findings.

    Returns ``(acknowledged_keys, problems)``. Evidence is absent (valid,
    no trailers) when the field is missing or empty and the body has no
    acknowledgement section. Present evidence must name only current
    HIGH/CRITICAL warning findings, once each, name the Architect in the
    ``architect`` field (the legacy ``pi`` field is not accepted for new
    evidence), and give each key exactly one non-empty bullet in the body
    section. Any problem means no key is acknowledged.
    """
    raw = frontmatter.get(ACK_FIELD)
    present_section, bullets = _ack_section(body)
    listed = raw if isinstance(raw, list) else []
    if not listed and not present_section and (raw is None or raw == "" or raw == []):
        return [], []

    problems = []
    if raw is not None and raw != "" and not isinstance(raw, list):
        problems.append(f"`{ACK_FIELD}` must be a [list] of finding keys")
    current = set(finding_keys(dangerous))
    seen = set()
    for key in listed:
        if not KEY_PATTERN.match(key):
            problems.append(f"`{key}` is not a RULE@path:line key")
        elif key in seen:
            problems.append(f"`{key}` is listed twice")
        elif key not in current:
            problems.append(f"`{key}` names no current dangerous-pattern warning "
                            "(stale, wrong line, or not a HIGH/CRITICAL warning)")
        seen.add(key)
    if not str(frontmatter.get("architect") or "").strip():
        problems.append("the `architect` field must name the Architect who decided")
    if not present_section:
        problems.append(f"the body has no `{ACK_HEADING}` section")
    elif not listed:
        problems.append(f"the body has a `{ACK_HEADING}` section but `{ACK_FIELD}` "
                        "lists no keys")
    by_key = {}
    for key, text in bullets:
        by_key.setdefault(key, []).append(text)
    for key in listed:
        texts = by_key.get(key, [])
        if present_section and len(texts) != 1:
            problems.append(f"`{key}` needs exactly one `- `{key}`: <decision>` bullet "
                            f"in the `{ACK_HEADING}` section")
        elif texts and not texts[0]:
            problems.append(f"the bullet for `{key}` has no decision text")
    for key in by_key:
        if key not in listed:
            problems.append(f"the bullet for `{key}` is not listed in `{ACK_FIELD}`")
    if problems:
        return [], problems
    return list(listed), []


def acknowledgement_trailers(keys, architect):
    """``Gator-Dangerous-Patterns`` / ``-Acknowledged-By`` trailer lines.

    Keys are joined with "," unshortened and otherwise byte-for-byte: each
    is bound to a staged path, and a path may contain spaces (even repeated
    ones), so internal whitespace is never normalized. Only CR/LF become a
    space, so a key cannot inject a trailer line. The Architect name uses
    the override sanitizer (80 chars).
    """
    if not keys:
        return []
    joined = ",".join(k.replace("\r", " ").replace("\n", " ") for k in keys)
    by = _override.sanitize_trailer_value(architect, _override.TRAILER_MAX["approved_by"])
    lines = [f"Gator-Dangerous-Patterns: {joined}"]
    if by:
        lines.append(f"Gator-Dangerous-Pattern-Acknowledged-By: {by}")
    return lines


def validate_skips(frontmatter, dangerous, acknowledged=()):
    """Bind a recorded skip (the agent proceeds without an Architect
    decision) to the current warning findings.

    Returns ``(skipped_keys, problems)``. An absent or empty
    ``dangerous-pattern-skips`` field is valid. Present keys must be current
    HIGH/CRITICAL warning findings, listed once, and not also acknowledged.
    No Architect name is required: a skip is, by definition, not the
    Architect's decision. Any problem skips nothing.
    """
    raw = frontmatter.get(SKIP_FIELD)
    if raw is None or raw == "" or raw == []:
        return [], []
    if not isinstance(raw, list):
        return [], [f"`{SKIP_FIELD}` must be a [list] of finding keys"]
    current = set(finding_keys(dangerous))
    acknowledged = set(acknowledged)
    problems, seen = [], set()
    for key in raw:
        if not KEY_PATTERN.match(key):
            problems.append(f"`{key}` in `{SKIP_FIELD}` is not a RULE@path:line key")
        elif key in seen:
            problems.append(f"`{key}` is listed twice in `{SKIP_FIELD}`")
        elif key not in current:
            problems.append(f"`{key}` in `{SKIP_FIELD}` names no current "
                            "dangerous-pattern warning")
        elif key in acknowledged:
            problems.append(f"`{key}` is both acknowledged and skipped")
        seen.add(key)
    if problems:
        return [], problems
    return list(raw), []


def skip_trailers(keys):
    """``Gator-Dangerous-Patterns-Unacknowledged`` for recorded skips; keys
    byte-for-byte except CR/LF, like acknowledgement_trailers()."""
    if not keys:
        return []
    joined = ",".join(k.replace("\r", " ").replace("\n", " ") for k in keys)
    return [f"Gator-Dangerous-Patterns-Unacknowledged: {joined}"]


# ---------------------------------------------------------------------------
# commit_draft.md parsing and the acknowledgement writer (#102)
# ---------------------------------------------------------------------------

def parse_simple_yaml(text):
    """Minimal parser for commit_draft frontmatter: flat ``key: value``
    pairs and single-line ``[a, b]`` lists. Returns None when malformed.
    The single parser for the hook (template copy) and the acknowledgement
    writer, so both read the draft the same way."""
    result = {}
    try:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                return None
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                items = [item.strip().strip("'\"") for item in value[1:-1].split(",")]
                result[key] = [i for i in items if i]
            elif ((value.startswith('"') and value.endswith('"'))
                  or (value.startswith("'") and value.endswith("'"))):
                result[key] = value[1:-1]
            else:
                result[key] = value
        return result
    except Exception:  # noqa: BLE001 — any parse failure is "malformed"
        return None


def split_draft(text):
    """``(frontmatter_text, frontmatter, body, error)`` for commit_draft text.

    With a ``---`` frontmatter block: its raw text, the parsed dict, the
    stripped body, and an error string when the block is malformed.
    Without one: ``(None, {}, body, None)``, where body drops ``# `` heading
    lines (the historical "# Session Change Log" rule).
    """
    if not text or not text.strip():
        return None, {}, "", None
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            yaml_text = parts[1].strip()
            body = parts[2].strip()
            frontmatter = parse_simple_yaml(yaml_text)
            if frontmatter is None:
                return yaml_text, {}, body, "Malformed YAML frontmatter in commit_draft.md"
            return yaml_text, frontmatter, body, None
    lines = text.splitlines()
    return None, {}, "\n".join(l for l in lines if not l.startswith("# ")).strip(), None


ACK_SURFACES = {"dashboard": "in the Dashboard", "agent": "in the agent session"}


def acknowledgement_text(surface="agent", note=None):
    """The decision text of one generated acknowledgement bullet."""
    text = f"Acknowledged by the Architect {ACK_SURFACES.get(surface, ACK_SURFACES['agent'])}."
    note = " ".join(str(note or "").split())
    return f"{text} {note}" if note else text


def render_acknowledgement(text, keys, architect, note=None, surface="agent"):
    """New commit_draft text recording one Architect decision for ``keys``.

    ``architect`` is the already-resolved, non-empty identity (ValueError
    when blank). It is written into the frontmatter ``architect:`` line:
    an empty value is replaced, an absent line is inserted, an equal value
    is kept; a different non-empty value raises ValueError (the caller
    refuses that case first). ``dangerous-pattern-acknowledgements`` is set
    or merged (earlier keys kept, in order), and one ``- `KEY`: <decision>``
    bullet per new key is appended to ``## Architect acknowledgement``
    (created at the end of the body when absent). Every other byte of the
    draft is kept; CRLF drafts stay CRLF. ValueError when the draft has no
    closed ``---`` frontmatter block.
    """
    architect = " ".join(str(architect or "").split())
    if not architect:
        raise ValueError("an Architect identity is required")
    crlf = "\r\n" in text
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("commit_draft.md has no frontmatter block")
    try:
        close = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("commit_draft.md frontmatter is not closed") from None

    def key_of(line):
        return line.partition(":")[0].strip() if ":" in line else None

    front = lines[1:close]
    arch_idx = next((i for i, l in enumerate(front) if key_of(l) == "architect"), None)
    if arch_idx is None:
        front.append(f"architect: {architect}")
    else:
        current = parse_simple_yaml(front[arch_idx]) or {}
        value = str(current.get("architect") or "").strip()
        if not value:
            front[arch_idx] = f"architect: {architect}"
        elif " ".join(value.split()) != architect:
            raise ValueError("the draft names a different Architect")
    ack_idx = next((i for i, l in enumerate(front) if key_of(l) == ACK_FIELD), None)
    existing = []
    if ack_idx is not None:
        raw = (parse_simple_yaml(front[ack_idx]) or {}).get(ACK_FIELD)
        existing = raw if isinstance(raw, list) else []
    new = [k for k in keys if k not in existing]
    line = f"{ACK_FIELD}: [{', '.join(existing + new)}]"
    if ack_idx is None:
        front.append(line)
    else:
        front[ack_idx] = line

    body = lines[close + 1:]
    bullets = [f"- `{k}`: {acknowledgement_text(surface, note)}" for k in new]
    head = next((i for i, l in enumerate(body) if l.strip() == ACK_HEADING), None)
    if head is None:
        while body and not body[-1].strip():
            body.pop()
        body += ["", ACK_HEADING, ""] + bullets + [""]
    else:
        end = next((i for i in range(head + 1, len(body))
                    if body[i].startswith("## ") or body[i].startswith("# ")), len(body))
        last = end
        while last > head + 1 and not body[last - 1].strip():
            last -= 1
        insert = bullets if last > head + 1 else [""] + bullets
        tail = [""] if end < len(body) else [""]
        body = body[:last] + insert + tail + body[end:]
        while len(body) > 1 and not body[-1].strip() and not body[-2].strip():
            body.pop()
    out = "\n".join(["---"] + front + ["---"] + body)
    if not out.endswith("\n"):
        out += "\n"
    return out.replace("\n", "\r\n") if crlf else out
