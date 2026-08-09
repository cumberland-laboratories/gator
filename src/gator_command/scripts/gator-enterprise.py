#!/usr/bin/env python3
"""
gator enterprise — thin dispatcher to the Enterprise CLI package.

Phase 4e (2026-08-02) consolidated Enterprise code under the top-level
`enterprise/` tree. This module — installed in the base wheel — is a
BACKWARDS-COMPAT DISPATCHER that:

  1. Preserves the `gator enterprise ...` CLI surface (help text,
     subcommand names) so scripts and docs referencing it don't break.
  2. Attempts to load the Enterprise CLI package (`gator_enterprise_cli`)
     and delegate real work to it.
  3. On ImportError — the common case in a bare `pip install gator-command`
     without the Enterprise CLI installed — prints a clean "Enterprise
     features not available in this install" message and exits 69
     (EX_UNAVAILABLE).

The `gator_enterprise_cli` package lives at:

    enterprise/enterprise-cli/gator_enterprise_cli/

and is NOT shipped in the base wheel. Installation is source-checkout-
only right now:

    pip install ./enterprise/enterprise-cli/    # from a source checkout

The `[enterprise-server]` extra installs SERVER-side dependencies only
(FastAPI, SQLAlchemy, Alembic, uvicorn, psycopg) so an operator can run
the Enterprise API service; it does NOT install the CLI package that
this dispatcher delegates to. Wiring a single-pipx-command install path
(`pipx install "gator-command[enterprise-cli]"` that also pulls in the
enterprise-cli wheel) is post-cutover integration work; Codex Phase 4e
review (2026-08-02, finding 3) flagged the earlier docstring's
suggestion of `[enterprise-server]` as an activation shortcut for
misleading operators.

Per Architect direction 2026-08-02: Enterprise pieces are not required
to work in an integrated fashion right now. The base install prints a
clear degraded-mode message; installers who want Enterprise features
install the enterprise-cli package separately from a source checkout.
"""

import argparse
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from gator_core import ensure_utf8_stdout
except ImportError:
    def ensure_utf8_stdout():
        return None


# ---------------------------------------------------------------------------
# Constants exported as part of the CLI contract (unchanged since Phase 3a).
# ---------------------------------------------------------------------------

PLAN_REF = (
    "gator-command/artifacts/"
    "2026-07-21-monorepo-convergence-implementation-plan.md"
)
EX_UNAVAILABLE = 69
UNAVAILABLE_SENTINEL = "[gator-enterprise-unavailable]"

CLIENT_SUBCOMMANDS = [
    ("activate",    "Activate Enterprise on this machine (one-time setup)"),
    ("sync",        "Pull hook-policy and org policies from Enterprise"),
    ("repo",        "Provision or upgrade a repo for Enterprise governance"),
    ("transcripts", "Manage session transcripts (pull, list, show, get, link)"),
    ("commits",     "Query commit ↔ transcript linkage"),
]

SERVER_SUBCOMMANDS = [
    ("auth",        "API auth token management"),
    ("repos",       "Repository inventory + reconcile"),
    ("providers",   "Git provider integrations (GitHub App etc.)"),
    ("policies",    "Org policy CRUD + rollout"),
    ("reports",     "Fleet reports"),
    ("machines",    "Machine registry"),
    ("blocks",      "Session block admin (transitional — retiring post-3.0)"),
]

ALL_SUBCOMMANDS = CLIENT_SUBCOMMANDS + SERVER_SUBCOMMANDS

# Verbs registered by the Enterprise CLI's own argparse (enterprise/
# enterprise-cli/gator_enterprise_cli/main.py, `subparsers` in main()).
# Sync obligation: any add/remove in enterprise-cli's registered set
# MUST be reflected here AND in the CLIENT/SERVER_SUBCOMMANDS help
# tables. `transcripts` and `commits` were added 2026-08-09 (Phase 4 —
# 3.0 stabilization P1.1) to close the MVP-unreachable gap; the P2.1
# reconciliation in the same commit rewrote the two help tables so
# every advertised verb is now in this set (integration-gap notice
# fires only when a future contributor advertises a verb without
# registering it here).
ENTERPRISE_CLI_VERBS = frozenset({
    "auth", "repos", "providers", "policies", "reports",
    "blocks", "machines", "activate", "sync", "repo",
    "transcripts", "commits",
})


# ---------------------------------------------------------------------------
# Enterprise CLI import + delegation
# ---------------------------------------------------------------------------


def _try_import_enterprise_cli():
    """Try to import the Enterprise CLI package. Return the module or None."""
    try:
        import gator_enterprise_cli  # noqa: F401
        return gator_enterprise_cli
    except ImportError:
        return None


def _unavailable_notice(verb: str) -> int:
    """Print the degraded-mode message and return EX_UNAVAILABLE."""
    print(f"{UNAVAILABLE_SENTINEL} gator enterprise {verb}: Enterprise features not available in this install.")
    print()
    print("The `gator_enterprise_cli` package is not importable. The base")
    print("`pip install gator-command` intentionally does not ship the")
    print("Enterprise CLI. It is source-checkout-only right now:")
    print()
    print("    pip install ./enterprise/enterprise-cli/    # from a source checkout")
    print()
    print("The `[enterprise-server]` extra installs server-side deps only")
    print("(FastAPI, SQLAlchemy, Alembic); it does NOT install the CLI.")
    print("A single-pipx install path is post-cutover packaging work.")
    print(f"Plan: {PLAN_REF}")
    print(f"Exit code {EX_UNAVAILABLE} (EX_UNAVAILABLE).")
    return EX_UNAVAILABLE


def _integration_gap_notice(verb: str) -> int:
    """Enterprise-cli IS importable but does not recognize the advertised
    verb -- Phase 4e integration gap. Return EX_UNAVAILABLE with a
    message distinct from _unavailable_notice so the operator can tell
    "package missing" from "package present but verb not wired up."
    """
    print()
    print(f"{UNAVAILABLE_SENTINEL} gator enterprise {verb}: verb not yet integrated with enterprise-cli.")
    print()
    print("The `gator_enterprise_cli` package is installed but its command")
    print("surface has not yet been reconciled with the base-wheel dispatcher's")
    print("advertised verbs (setup/status/sync/audit/disconnect + server/db/")
    print("policy/org/fleet). enterprise-cli currently exposes a different")
    print("verb set (auth/repos/providers/policies/reports/blocks/machines/")
    print("activate/sync/repo) inherited from the enterprise-mvp port.")
    print()
    print("Reconciling the two is post-cutover integration polish per")
    print(f"Architect direction. Plan: {PLAN_REF}")
    print(f"Exit code {EX_UNAVAILABLE} (EX_UNAVAILABLE).")
    return EX_UNAVAILABLE


# ---------------------------------------------------------------------------
# Parser + dispatch
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gator enterprise",
        description=(
            "Manage Enterprise capability. Thin dispatcher — real command "
            "bodies live in `enterprise/enterprise-cli/gator_enterprise_cli/`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "client-side commands (advertised; delegates to enterprise-cli):\n"
            + "\n".join(f"  {name:<12} {help_text}"
                        for name, help_text in CLIENT_SUBCOMMANDS)
            + "\n\nserver-side commands (advertised; delegates to enterprise-cli):\n"
            + "\n".join(f"  {name:<12} {help_text}"
                        for name, help_text in SERVER_SUBCOMMANDS)
            + "\n\ninstall the Enterprise CLI (source-checkout-only right now):\n"
            + "  pip install ./enterprise/enterprise-cli/   (from a source checkout)\n"
            + "\nnote: `[enterprise-server]` installs server deps only, not this CLI.\n"
            + "      A single-pipx path is post-cutover packaging work.\n"
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="<subcommand>")

    # Every subcommand gets a bare add_parser here for --help support.
    # Actual arg-parsing for real commands happens inside the Enterprise
    # CLI package when it's loaded and delegated to. Strict argparse
    # rejection of unknown flags on THIS layer would prevent legitimate
    # per-subcommand flags from reaching the delegatee, so bare parsers
    # + REMAINDER passthrough is the right shape here.
    for name, help_text in ALL_SUBCOMMANDS:
        sp = sub.add_parser(name, help=help_text, description=help_text,
                            add_help=False)
        sp.add_argument("passthrough", nargs=argparse.REMAINDER,
                        help=argparse.SUPPRESS)

    return parser


def main(argv=None) -> int:
    ensure_utf8_stdout()
    argv = argv if argv is not None else sys.argv[1:]

    parser = _build_parser()
    args, _remaining = parser.parse_known_args(argv)

    if not args.subcommand:
        parser.print_help()
        return 0

    # Three ordered checks before delegation. Each has a distinct
    # degraded-mode notice so operators can tell them apart.
    #
    #   (a) Package not importable -> _unavailable_notice (EX_UNAVAILABLE).
    #       Base wheel without enterprise-cli installed. Common case.
    #   (b) Package importable but .main submodule missing -> stderr
    #       "incomplete install" (EX_UNAVAILABLE). Broken install.
    #   (c) Advertised verb not in ENTERPRISE_CLI_VERBS ->
    #       _integration_gap_notice (EX_UNAVAILABLE). Phase 4e verb-set
    #       mismatch; reconciliation is post-cutover polish.
    #
    # Order matters: install-integrity (a, b) precedes verb integration
    # (c). A broken install is more fundamental than a verb gap and
    # reporting the verb gap would mask it.
    #
    # Codex whiteboard finding 1 (2026-08-02) history: the previous fix
    # caught ALL nonzero SystemExit from delegation and translated to
    # _integration_gap_notice. That was too broad -- a mapped verb's
    # real runtime error (e.g. `sync` -> SystemExit(1) on network
    # failure) got mislabeled as "verb not yet integrated," hiding the
    # real cause from operators. This pre-check version filters unmapped
    # verbs upfront so delegation runs ONLY for verbs enterprise-cli
    # actually handles; SystemExit from that delegation is then the real
    # command's exit code and must reach the caller unmodified.

    # (a) Package importable?
    ent = _try_import_enterprise_cli()
    if ent is None:
        return _unavailable_notice(args.subcommand)

    # (b) .main submodule importable?
    try:
        from gator_enterprise_cli.main import main as ent_main
    except ImportError as e:
        print(
            f"{UNAVAILABLE_SENTINEL} gator enterprise: `gator_enterprise_cli` "
            f"loaded but its `main` module is missing ({e}). Install is "
            f"incomplete.",
            file=sys.stderr,
        )
        return EX_UNAVAILABLE

    # (c) Advertised verb mapped in enterprise-cli?
    if args.subcommand not in ENTERPRISE_CLI_VERBS:
        return _integration_gap_notice(args.subcommand)

    # Signature mismatch handling: some enterprise-cli builds accept
    # main(argv); others take no arguments and read sys.argv themselves.
    # Try argv-passthrough first, fall back to sys.argv swap on TypeError.
    # SystemExit from either path carries the REAL exit code -- propagate
    # unmodified. Do NOT translate to integration-gap; the verb-mismatch
    # case was already handled by the pre-check above.
    try:
        try:
            result = ent_main(argv)
        except TypeError:
            saved = sys.argv
            try:
                sys.argv = ["gator-enterprise", *argv]
                result = ent_main()
            finally:
                sys.argv = saved
        # ent_main() convention: may return None on success; normalize to 0.
        return 0 if result is None else int(result)
    except SystemExit as e:
        if e.code is None:
            return 0
        return e.code if isinstance(e.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
