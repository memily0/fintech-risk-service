# Local Integration Workbench

This is the I02-I04.1 local integration build, not production ArcShift V1.
It has a FastAPI service, persistent SQLite fixtures, synthetic .test accounts,
owner-scoped watchlists/reviews and a responsive browser workbench. It does not
replace the existing Streamlit app, train models, fetch provider data, load old
weights, send real email or deploy infrastructure.

## Run

From the product repository root, using a separate environment:

```sh
python3 -m venv .venv-v1
.venv-v1/bin/python -m pip install -r requirements-v1.lock
.venv-v1/bin/python -m arcshift_v1
```

The workbench is at http://127.0.0.1:8765/; health is at /healthz. If that port is occupied,
select another local port rather than stopping somebody else's process:

```sh
ARCSHIFT_PORT=8766 .venv-v1/bin/python -m arcshift_v1
```

Supported settings: ARCSHIFT_ENVIRONMENT=local/test,
ARCSHIFT_DATA_MODE=synthetic, ARCSHIFT_HOST=127.0.0.1/localhost,
ARCSHIFT_PORT=1024..65535, ARCSHIFT_STORAGE_BACKEND=sqlite/memory,
ARCSHIFT_DB_PATH=<local-file>. Other environments, live mode and public bind
addresses fail at startup. There is no automatic .env or credential loading.
Do not bypass these restrictions with a separate public Uvicorn command.

## Local Storage And Migrations

Default storage is SQLite at .arcshift-v1/fixtures.sqlite3 in the product root.
Relative database paths are anchored to the product root, not the shell's
current directory. The default runtime directory is excluded from Git.
Custom database files must also stay outside publication artifacts; their
location does not become safe for private data just because it is configurable.
Use ARCSHIFT_STORAGE_BACKEND=memory for explicitly nonpersistent fixture tests.

At startup the service validates the synthetic seed, applies pending migrations
transactionally, and imports one immutable content-hashed fixture snapshot.
Repeated startup does not overwrite its payload or original import timestamp.
Changing content under the same fixture_version is an error, not an update.
The active-snapshot pointer has a foreign key. Unknown databases, newer schema
versions, altered migration checksums and inconsistent ledgers fail closed.

Run the schema command separately when needed, with the same environment:

```sh
.venv-v1/bin/python -m arcshift_v1.database
.venv-v1/bin/python -m arcshift_v1.database --check
```

The first command applies schema migrations, without importing a fixture.
The second is read-only and does not create a missing database. Server startup
then imports/validates the fixture. There is no destructive down/rebuild command.
A failed migration rolls back its transaction; this does not replace a backup
or constitute a tested production restore. Never edit an applied SQL migration:
add the next version and its tests instead.

SQLite here is the local synthetic adapter, not a decision on the production
database or a guarantee of multi-user performance. Migrations 002/003 add
synthetic accounts, sessions, watchlists, reviews and their status events.
Production storage, backups,
retention, region and workload requirements still need their own decisions.

## Candidate API

| Path | Meaning |
| --- | --- |
| GET /healthz | Process health, explicitly fixture-only |
| GET /readyz | Fixture store ready, not production readiness |
| GET /api/v1/capabilities | Implemented boundaries and unavailable features |
| GET /api/v1/demo/scenarios | Six shared synthetic scenarios |
| GET /api/v1/demo/scenarios/{scenario_id} | One scenario by ID, no file-path lookup |
| GET /openapi.json | Machine-readable candidate response schemas |

Scenario IDs: loading, empty, stale, unsupported, error, historical_demo.
The scenario's state is an example for UI development: the error scenario
itself returns HTTP 200 with state=error, not a simulated operational outage.
Unknown IDs return 404, unavailable store 503, unsupported methods 405.

All data envelopes include synthetic=true, data_mode=synthetic,
production_ready=false, source_rights_status=not_admitted and the candidate
api_contract_version=v1-fixture.1. This API version is not a human-approved
release contract. None of the five non-demo states has a signal. The demo
has a synthetic, uncalibrated score and no fitted model or drivers.

Responses are no-store with an explicit synthetic header. Host validation
is enabled; no wildcard CORS, static data/model directories, uploads or
user-private resources are exposed. This is not a full security review.
The fixture namespace remains anonymous and read-only. Local authentication
and private writes use separate namespaces and candidate contracts described
in [LOCAL_AUTH.md](LOCAL_AUTH.md). The old fixture capabilities refer to that
namespace, not a declaration that public account functionality is complete.
Swagger/Redoc UI is disabled so reading the local OpenAPI JSON needs no CDN.

Startup prepares storage once per app lifespan. SQLite read requests use
read-only connections and verify schema and snapshot integrity; they do not
create missing databases, migrate or reimport the seed. A missing/corrupt store
returns a generic 503 without database paths or payload details. /healthz may
remain healthy while /readyz fails, distinguishing process health from storage.
Memory mode loads the fixture once per lifespan. Requests never
run provider downloads, rebuild CSVs, fit models or schedule jobs. The store
protocol is the replacement boundary for later admitted data; current response
models deliberately refuse production/live score claims.

## Fixture Provenance

fixtures/ui_scenarios.json preserves the shared v1-handoff.1 content from
the team package product_build/arcshift_v1/fixtures/ui_scenarios.json.
It is deliberately copied into this small runtime package so cloning/running
the product does not require the private research workspace or output archives.
No observation schema, source-binding or model-target definition was changed.
Do not replace these examples with real user or provider data.

## Verify

```sh
.venv-v1/bin/python -m unittest discover -s tests -v
.venv-v1/bin/python tools/smoke_v1_backend.py
.venv-v1/bin/python tools/smoke_v1_auth.py
.venv-v1/bin/python -m pip check
```

The smoke check starts two successive temporary servers on free loopback ports,
checks real HTTP responses, and verifies one SQLite snapshot and the migration
history survive restart without duplication. Both child processes stop, and
the temporary test database is removed. It does not touch your default runtime
database or leave a public server running. Tests use synthetic examples only, not the 40 V1 acceptance
scenarios or a model evaluation. The dependency lock was resolved/tested on
Python 3.14.0, separately from legacy requirements.txt. It pins versions,
not wheel hashes, and is not production dependency/security acceptance.

Known dependency warning: the installed Starlette TestClient deprecates its
HTTPX compatibility path. Current tests pass; replacing that test transport
or separately reviewing its successor remains dependency-review work, not
an ignored production compatibility guarantee.

The browser check is `node tools/smoke_v1_workbench.cjs` with Playwright available
to Node. Set `ARCSHIFT_PLAYWRIGHT_CHANNEL=chrome` to use installed Google Chrome
instead of a Playwright-managed browser. Optional `ARCSHIFT_BROWSER_EVIDENCE_DIR`
saves screenshots and a browser-generated synthetic PDF, but never the test DB
or session tokens. It exercises registration, local verification, login,
watchlists, review revisions, export, ownership and cross-tab logout on desktop
and mobile. Browser print is available, not server-side PDF generation.

## Private Workflow

- `/api/v1/workspace/watchlist`: owner-scoped GET and CSRF-protected PUT.
- `/api/v1/workspace/reviews`: bounded GET and CSRF-protected POST.
- `/api/v1/workspace/reviews/{UUID}`: owner-scoped GET/PATCH.
- `/api/v1/workspace/reviews/{UUID}/report.json` and `/report.csv`: owner-only.

Each review freezes the exact synthetic scenario and content-addressed SQLite
snapshot. Edits require `expected_revision`; stale edits return 409 without
overwriting the newer note. Status transitions and times are recorded; closing
a review is not evidence of model correctness. Events retain status/revision,
not a complete history of previous note text. Foreign IDs return 404, anonymous
requests 401. Export labels remain synthetic and not admitted; CSV neutralizes
formula prefixes. Notes render as text, never as HTML. The browser clears
private state on logout, including same-origin tabs, and stores no private
notes or credentials in localStorage. Watchlist replacement is last-write-wins;
review notes have optimistic concurrency protection.

## Remaining Integration Work

- K0 review of the candidate API and schema by data/model/UI contributors.
- Production database selection and fuller application schemas; the local
  synthetic SQLite adapter is not production storage acceptance.
- Public-account admission, real verified email, resend/password recovery,
  HTTPS cookies, retention/deletion policies and independent security review.
- Source-backed workflow integration, production authorization/load testing,
  fuller application schemas and report acceptance beyond synthetic examples.
- Actual admitted sources and accepted model artifacts behind versioned boundaries.
- Independent security review, operations, restore/rollback and release acceptance.

Data/validation changes assigned to other contributors are not implemented
by this skeleton. The legacy maturity/unknown-target findings remain open.

Technical references: Python's [sqlite3 interface](https://docs.python.org/3.14/library/sqlite3.html)
and SQLite [transaction control](https://www.sqlite.org/lang_transaction.html).
These document mechanisms, not measured production durability or readiness.
