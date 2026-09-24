# Charter: Enterprise Dispatcher

**Covers**: `src/gator_command/scripts/gator-enterprise.py`

## Owns

- The `gator enterprise` command surface shipped in the base wheel.
- Delegation to the separately installed `gator_enterprise_cli` package.
- Stable degraded-mode behavior when that package is unavailable or incomplete.

## Does Not Own

- Enterprise command bodies, credentials, activation, or transcript discovery; see [`scripts-enterprise-cli.md`](scripts-enterprise-cli.md).
- Enterprise API, models, workers, or migrations; see [`scripts-enterprise-server.md`](scripts-enterprise-server.md).
- General CLI routing and packaging; see [`scripts-cross-cutting.md`](scripts-cross-cutting.md).

---

### _build_parser()
File: src/gator_command/scripts/gator-enterprise.py
Builds the stable public verb surface while leaving command-specific arguments to the delegate.
<- `main()`
-> `CLIENT_SUBCOMMANDS`, `SERVER_SUBCOMMANDS`
! Use permissive parsing at this layer. Strict subcommand parsing belongs to `gator_enterprise_cli`.

### _try_import_enterprise_cli()
File: src/gator_command/scripts/gator-enterprise.py
Loads the optional implementation package without importing Enterprise server dependencies into the base wheel.
<- `main()`
-> `gator_enterprise_cli.main`
! Missing and incomplete installs are expected degraded states, not tracebacks.

### _unavailable_notice(verb) / _integration_gap_notice(verb)
File: src/gator_command/scripts/gator-enterprise.py
Emit machine-recognizable diagnostics and return `EX_UNAVAILABLE` (`69`).
<- `main()`
! Keep the unavailable sentinel and exit code stable for scripts that detect optional capability.

### main(argv=None)
File: src/gator_command/scripts/gator-enterprise.py
Validates that an advertised verb is mapped, delegates the original arguments, and returns the delegate's real exit code.
<- `gator enterprise ...`
-> `_build_parser()`, `_try_import_enterprise_cli()`
! Do not translate `SystemExit` from a mapped command into an integration-gap error; that would hide real command failures.
! The advertised verb set and the implementation package's registered verbs must change together.

## Before Changing This Module

- Preserve base-install `--help` without Enterprise dependencies.
- Verify unavailable, incomplete-install, integration-gap, and delegated-exit-code paths.
- Run source tests and the installed-wheel Enterprise dispatcher checks.

## Connections

-> [Enterprise CLI](scripts-enterprise-cli.md) - delegated implementation
-> [Enterprise Server](scripts-enterprise-server.md) - API consumed by the CLI
-> [Cross-Cutting](scripts-cross-cutting.md) - base/optional product boundary
-> [Contracts](contracts.md) - marker and packaging compatibility
