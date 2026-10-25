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
