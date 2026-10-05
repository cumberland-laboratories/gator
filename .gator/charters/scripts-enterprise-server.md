# Charter: Enterprise Server

**Covers**: `enterprise/app/**`, `enterprise/migrations/**`, `enterprise/Dockerfile`, `enterprise/alembic.ini`, `enterprise/fly.toml`, `enterprise/requirements.txt`

## Owns

- FastAPI routing, authentication, tenant isolation, rate limiting, and error envelopes.
- SQLAlchemy models and the append-only Alembic migration chain.
- Provider synchronization, evidence extraction, transcript custody/linkage, policy rollout/state, drift, and reports.
- Background ingest and reconciliation jobs.

## Does Not Own

- Local transcript discovery or operator command UX; see [`scripts-enterprise-cli.md`](scripts-enterprise-cli.md).
- Base-wheel dispatch and packaging; see [`scripts-enterprise.md`](scripts-enterprise.md).
- Base Gator repository governance.

---

### app (FastAPI application)
File: enterprise/app/main.py
Constructs the FastAPI app, middleware, exception handlers, and routers.
<- ASGI server
-> routes, auth, rate limits, database
! Server modules remain optional to the base wheel and are imported only in the Enterprise server environment.

### verify_token() / hash_token()
File: enterprise/app/auth.py
Authenticates API tokens and establishes organization scope.
<- protected routes
-> `ApiToken`, database session
! Every tenant-owned read and write is constrained by the authenticated organization; object IDs alone are never authorization.

### ApiError / exception handlers
File: enterprise/app/api_contract.py
File: enterprise/app/errors.py
Define stable validation helpers and JSON error envelopes with request correlation.
<- routes and middleware
! Expected client failures use the contract envelope; unhandled exceptions do not leak secrets or internals.

### ingest_commits() / ingest_transcript() / link_transcript() / relink_transcript()
File: enterprise/app/routes/ingest.py
Ingest evidence, persist transcript blobs, derive linkage candidates, and expose explicit linkage correction.
<- Enterprise CLI
-> blob store, transcript and commit models
! Ingest is retry-safe. Content hashes and vendor/session identity drive deduplication.
! Linkage basis is recorded; explicit relink never masquerades as automatic linkage.

### FilesystemBlobStore / build_blob_key()
File: enterprise/app/services/blob_store_filesystem.py
File: enterprise/app/services/blob_store.py
Store transcript payloads outside relational rows behind a replaceable blob-store protocol.
<- ingest and transcript reads
! Blob keys are deterministic and tenant-scoped. Missing blobs produce a typed not-found result.

### policy service operations
File: enterprise/app/services/policy.py
Create immutable versions, activate one version, manage targets, and enqueue drift refresh.
<- policy routes
-> policy models, ingest jobs
! Deactivate and flush the prior active version before activating another; uniqueness is checked per statement.
! Route declarations for fixed paths such as `/active` precede dynamic `/{policy_id}` routes.

### report_policy_state() / list_policy_state() / policy_drift()
File: enterprise/app/routes/policy_state.py
Upsert current machine/repository policy proof and answer fleet drift queries.
<- policy CLI
-> `MachinePolicyState`, active policy versions
! Upsert lookup columns exactly match the database uniqueness constraint.
! Drift is report-based: machines that never reported are absent, not implicitly in sync.
! Activating a new version changes drift classification without requiring machines to re-report.

### transcript read routes
File: enterprise/app/routes/transcripts.py
List transcript sessions, retrieve metadata/blob content, and show commit links.
<- Enterprise CLI and operator clients
-> transcript models, blob store
! Blob access remains organization-scoped and preserves stored encoding metadata.

### sync and provider operations
File: enterprise/app/services/sync.py
Normalize provider events, synchronize repositories/commits, and enqueue idempotent work.
<- webhooks, worker, admin operations
-> provider adapter, repositories, ingest jobs
! Verify provider signatures before mutation. Duplicate webhook delivery must not create duplicate commit work.

### worker.run() / process_job()
File: enterprise/app/worker.py
Claims and executes ingest, extraction, drift, report, and reconciliation jobs.
<- worker process
-> service layer
! Job claiming prevents concurrent double execution; retries preserve idempotency and record terminal failure honestly.

### fleet and report read services
File: enterprise/app/services/fleet_reads.py
File: enterprise/app/services/audit_reads.py
File: enterprise/app/services/reporting.py
Compute tenant-scoped fleet, timeline, compliance, and immutable report snapshots.
<- views and report routes
! Pagination cursors and report hashes are deterministic; cached reads never cross tenant boundaries.

### migrations 001-012
File: enterprise/migrations/versions/*.py
Define the ordered production schema history.
<- Alembic
-> Enterprise database
! Never edit an applied migration; append a new revision.
! Model and migration constraints/defaults must agree. New timestamped tables include database-side timestamp defaults and receive a real-Postgres smoke test; SQLite `create_all` is not migration evidence.
! Nullable columns inside uniqueness contracts require explicit treatment because PostgreSQL permits multiple NULL values.

## Before Changing This Module

- Trace organization scoping from authentication through every query and blob key.
- Check retry/idempotency behavior for webhooks, ingest, and workers.
- Add a migration for persistent shape changes and smoke it on PostgreSQL.
- Run Enterprise tests plus contract tests for schemas consumed by the CLI.

## Connections

-> [Enterprise CLI](scripts-enterprise-cli.md) - API consumer and local evidence source
-> [Enterprise Dispatcher](scripts-enterprise.md) - optional product boundary
-> [Contracts](contracts.md) - shared wire and policy schemas
-> [Release Pipeline](release-pipeline.md) - separate Enterprise validation
