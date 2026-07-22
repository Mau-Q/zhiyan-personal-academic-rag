# Stage 1 Remote Validation Package

This package is executed by the repository owner on the isolated remote host. It
does not authorize an agent to connect to, deploy, restart, or reconfigure remote
services.

## Scope and stop conditions

The canary uses a dedicated `stage1_canary_<run-id>` owner, deterministic hidden
Elasticsearch index, and detached Milvus collection. A successful run proves:

1. PostgreSQL migrations are present and the PDF creates one owner-scoped version;
2. inactive Chunks are staged into both physical stores;
3. both stores activate before PostgreSQL commits `READY`;
4. reconciliation proves the exact PostgreSQL version and both physical routes;
5. deletion makes PostgreSQL invisible first, then completes two physical cleanup jobs;
6. the deleted document cannot be reconciled as online.

Stop immediately if the repository commit is not the reviewed commit, any service
is exposed beyond loopback, the PDF SHA-256 differs, migration drift is reported,
or the run creates/modifies a non-Canary physical object. Do not paste credentials,
PDF text, Chunk text, IP addresses, or complete connection strings into chat.

## Prerequisites

- Use the reviewed repository commit and its project `.venv`.
- Install the `postgres` and `milvus` optional dependencies in that environment.
- Keep `DATABASE_URL` and optional `MILVUS_TOKEN` in environment variables.
- `ELASTICSEARCH_URL`, `MILVUS_URI`, and `OLLAMA_URL` must point to loopback services.
- Select one non-sensitive text PDF and independently calculate its SHA-256.

## Ordered execution

Run each command separately. PowerShell examples are shown; replace placeholders
locally and do not return the environment-variable assignment lines.

1. Confirm the exact source revision and clean worktree:

   ```powershell
   git rev-parse HEAD
   git status --short
   ```

2. Run repository and Stage 1 local gates before mutation:

   ```powershell
   .\.venv\Scripts\python.exe scripts\validate_harness_contract.py
   .\.venv\Scripts\python.exe -m unittest -v tests.validation.test_stage1_reconciliation
   ```

3. Set credentials and loopback endpoints in the current shell, then apply all
   versioned PostgreSQL migrations. `UNCHANGED` is valid on replay; checksum drift
   is a hard failure:

   ```powershell
   .\.venv\Scripts\python.exe -m backend.storage.migrate
   ```

4. Run the complete Canary with a new non-secret run ID. The command is deliberately
   mutating and refuses to run without the literal confirmation phrase:

   ```powershell
   .\.venv\Scripts\python.exe scripts\run_stage1_remote_canary.py --pdf <PDF_PATH> --expected-sha256 <PDF_SHA256> --run-id <NEW_RUN_ID> --confirm RUN_ISOLATED_STAGE1_CANARY --output runtime\stage1-remote-validation\report.json
   ```

5. Return only these sanitized artifacts:

   ```powershell
   git rev-parse HEAD
   Get-FileHash runtime\stage1-remote-validation\report.json -Algorithm SHA256
   Get-Content runtime\stage1-remote-validation\report.json
   ```

Expected final fields are `status=PASS`, `cleanup_jobs_succeeded=2`, and
`inactive_visibility_proven=true`. Physical route names and synthetic Canary IDs
are safe to return; no Chunk payload is included.

## Replay and single-side failure check

The main run already proves successful replay-safe lifecycle boundaries. To verify
single-side recovery, use a fresh run ID, temporarily point `MILVUS_URI` at an
unused loopback port, and run step 4 once. Expected result: `status=FAIL`; PostgreSQL
must not expose the version as READY. Restore the correct loopback URI and repeat
the exact same command and run ID. Expected result: `PASS`; Elasticsearch staging
is reused, Milvus completes, and final cleanup succeeds.

Do not simulate failure by stopping a stable service. Do not use a production owner,
index prefix, collection prefix, PDF, or idempotency key.

## Failure and rollback

On any `FAIL`, preserve the sanitized JSON and stop. Do not manually delete database
rows. Retry the same run ID only after correcting the classified dependency issue;
the repository contracts are designed to resume partial staging. If retry cannot
finish, return the report plus redacted service health output so a versioned cleanup
procedure can be prepared. Manual database or wildcard index deletion is prohibited.
