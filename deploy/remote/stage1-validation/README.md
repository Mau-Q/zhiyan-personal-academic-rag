# Stage 1 Remote Validation Package

This package is executed by the repository owner on the isolated remote host. It
does not authorize an agent to connect to, deploy, restart, or reconfigure remote
services.

## Scope and stop conditions

The canary uses a dedicated `stage1_canary_<run-id>` owner, deterministic hidden
Elasticsearch index, and detached Milvus collection. A v2 successful run proves:

1. all PostgreSQL migrations are present and the PDF creates one owner-scoped version;
2. the PDF object reopens from an opaque persistent key and the exact Chunk snapshot reloads from PostgreSQL;
3. inactive Chunks are staged into both physical stores before PostgreSQL commits `READY`;
4. the Answer API reads the persisted READY snapshot and returns Evidence without Fixture Chunk or Scope files;
5. deletion makes PostgreSQL invisible first, then completes ES, Milvus and runtime-snapshot cleanup jobs;
6. the deleted document fails both reconciliation and the Answer API visibility check.

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
- The default PDF object root is the ignored `runtime/stage1-pdf-objects` directory. Use `--pdf-object-root` only for a dedicated private persistent path; never return that path in chat.

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
   $PdfPath = Read-Host 'PDF path'
   $ExpectedPdfSha256 = Read-Host 'Expected PDF SHA-256'
   $RunId = Read-Host 'New non-secret run ID'
   .\.venv\Scripts\python.exe scripts\run_stage1_remote_canary.py --pdf $PdfPath --expected-sha256 $ExpectedPdfSha256 --run-id $RunId --confirm RUN_ISOLATED_STAGE1_CANARY --output runtime\stage1-remote-validation\report.json
   ```

5. Return only these sanitized artifacts:

   ```powershell
   git rev-parse HEAD
   Get-FileHash runtime\stage1-remote-validation\report.json -Algorithm SHA256
   Get-Content runtime\stage1-remote-validation\report.json
   ```

Expected report schema is `stage1_remote_canary_report_v2`. Required fields include
`status=PASS`, `pdf_object_reopen_proven=true`, `answer_api_status=COMPLETED`,
`answer_api_evidence_count>=1`, `cleanup_jobs_succeeded=3`,
`runtime_snapshot_cleanup_proven=true`, `inactive_visibility_proven=true`, and
`inactive_answer_api_status=403`. `resumed_from_ready=true` is expected when the
same Run ID continues after a previous failure between READY and inactivation.
When real generation is enabled, both calls must independently pass the Answer API
and citation gates and return the same Citation set. The report records this as
`generation_stable_replay=true`; `generation_byte_stable_replay` separately records
whether the natural-language answers were byte-identical and is not a hard gate.
If generation fails closed, the private Canary report records only an allowlisted
stable category such as Chat transport, response JSON, answer JSON, answer Schema,
citation, or identity failure. It never records the exception text, generated
answer, Prompt, Evidence, or upstream response body.
Synthetic Canary IDs and snapshot hashes are safe
to return; object paths and Chunk payloads are not included.

## Online Reranker combined-latency Gate

After the fixed component Gate passes, the controlled online integration has a
separate Windows PowerShell 5.1 entrypoint:

```powershell
powershell.exe `
    -NoLogo `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File .\deploy\remote\reranker-validation\run_online_reranker_gate.ps1 `
    -PdfPath '.\runtime\online-reranker-gate-input\2603.04915.pdf' `
    -ExpectedPdfSha256 'ff3b39d94690de98cff09998c669b20333861d43b797ea000af812bc7f524dcf' `
    -QuestionSuitePath '.\runtime\online-reranker-gate-input\doc_arxiv_2603_04915.json' `
    -ExpectedQuestionSuiteSha256 '4f4d293bc8bc00ba2f4469977d43d9c1ffa40556a70762f15d2f47ed954c6bd3' `
    -DocumentTitle 'EVMbench: Evaluating AI Agents on Smart Contract Security' `
    -RunId 'online_retrieval_profile_20260723_01'
```

Run it only after the reviewed Mac commit has been pushed and Windows
`HEAD` equals `origin/main`. The command above pins the existing ignored private
inputs and requires a new non-secret Run ID. If `DATABASE_URL` is absent, the
script securely prompts for the password of
`zhiyan_stage1_canary_app@127.0.0.1:5432/zhiyan_stage1_canary`, URL-encodes it,
sets the connection only for the Gate, and removes it afterward; it never prints
the password or complete connection string. An existing `DATABASE_URL` is reused
and left untouched.

This Gate disables real generation and changes only the optional post-RRF
Reranker. It repeats the three cases ten times and requires at least 30
observations, all with `APPLIED`, no fallback, no candidate expansion,
candidate count at most 20, output count at most 3, and combined
`P95 <= 300 ms` from PostgreSQL READY routing through ES/Milvus retrieval, RRF,
and reranking. It must also complete INACTIVE, all three cleanup jobs, and the
deleted-document Answer API 403 check. Return only the script's final sanitized
summary or a screenshot of it; do not return credential assignment lines,
private paths, questions, document text, model cache paths, or service URLs.

The ES/Milvus-parallel run `online_reranker_parallel_20260723_01` completed
30/30 `APPLIED` observations with no fallback, expansion, or candidate-bound
violation, followed by three successful cleanup jobs and inactive Answer 403.
It still failed `ONLINE_RERANKER_COMBINED_P95_EXCEEDED`: base retrieval
P95 was `344.676365 ms`, Reranker P95 was `131.885375 ms`, and combined P95
was `472.190015 ms`. Its report SHA-256 is
`132DFFDECDAD02F9C5280FADFBD09B5AE100C1DB31FE07118BF97B6E0C1B2602`.

Because base retrieval alone exceeds the full 300 ms budget, the next run above
does not change retrieval behavior. It only records P50/P95 for READY route
resolution, Chunk snapshot loading, Elasticsearch validation/query, Milvus
validation, query embedding, Milvus ANN search, backend parallel wall time,
READY revalidation, RRF fusion, and retriever total. Return all stage P95 fields
from the final sanitized summary. The 300 ms limit and default route remain
unchanged.

## Replay and single-side failure check

The earlier v1 run already proved single-side recovery. For the v2 Gate, one normal
fresh run is sufficient unless the new migration, snapshot persistence, Answer API,
or three-way cleanup reports a failure. A failure after PostgreSQL commits `READY`
must be replayed with the same Run ID: the script reopens the exact PDF and Chunk
snapshot, revalidates both physical routes, and resumes at the Answer gate without
re-ingestion or index recreation. Do not repeat the old fault simulation only to
create redundant evidence.

Do not simulate failure by stopping a stable service. Do not use a production owner,
index prefix, collection prefix, PDF, or idempotency key.

## Failure and rollback

On any `FAIL`, preserve the sanitized JSON and stop. Do not manually delete database
rows or object files. The same run ID is replayable before `INACTIVE`; cleanup jobs
remain leased and retryable after `INACTIVE`. Return the report plus redacted service
health output so the exact recovery command can be selected. Manual database,
object-path, or wildcard index deletion is prohibited.
