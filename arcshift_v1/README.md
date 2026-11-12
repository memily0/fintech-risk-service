# Local Integration Workbench

This is the I02-I05.3 local integration build, not production ArcShift V1.
It has a FastAPI service, persistent SQLite fixtures, synthetic .test accounts,
owner-scoped watchlists/reviews and a responsive browser workbench. It does not
replace the existing Streamlit app, train models, fetch provider data, load old
weights, send real email or deploy infrastructure.

## Run

From the product repository root, using a separate environment:

```sh
python3 -m venv .venv-v1
.venv-v1/bin/python -m pip install -r requirements-v1.lock
.venv-v1/bin/python -m pip install --no-build-isolation --no-deps -e .
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

## Data Lane Integration

Nastya's D01-D03 code at `8bdb1de597eb5d567a8a19c84435ad9294a206cc`
is preserved under `src/arcshift_data`; see [integration record](../docs/v1_data_integration.md).
The editable package connects it without PYTHONPATH manipulation. Local startup
uses its actual FX/curve/CPI parsers and revision store on explicitly invented
provider-shaped fixtures, then atomically publishes an immutable SQLite read
snapshot. Real receipts remain prohibited. The market registry snapshot is
packaged explicitly, so the API also works from an unpacked wheel outside the
checkout. The data helper's default external config path is for source checkouts;
the API passes its packaged synthetic registry explicitly.

- `GET /api/v1/market/series`: seven synthetic series, metadata and row counts.
- `GET /api/v1/market/series/{series_id}/history`: date filtering, bounded
  pagination and optional `include_revisions=true`.
- Candidate market contract: `v1-local-market.1`, always synthetic,
  `validity_status=historical_demo`, `source_rights_status=not_admitted`.

The browser History view reads this API. Receipt time and unknown publication
stay distinct. Restart preserves the active snapshot and does not roll it back
to the original seed. Content hashes, contiguous revisions, latest-map
consistency and series/resource/unit bindings are checked on reads. These are
not real provider connectivity, a scheduler, freshness admission or model input
acceptance. The runtime never exposes the producer JSON as a file browser.

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

The backend smoke starts two successive temporary servers on free loopback ports,
checks real HTTP responses, and verifies fixture/market snapshots and migration
history survive restart without duplication. The auth smoke captures a local
review and selected synthetic market history in a saved report, updates the
review, then checks the original report and its three export formats after a
process restart. It also checks cross-user denial and explicit reuse of a
revoked cookie. Both smoke checks clean up their servers and temporary SQLite
databases. The [local acceptance record](../docs/v1_local_acceptance.md) lists
the scenarios covered. The dependency lock was resolved/tested on
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
- `/api/v1/workspace/series-watchlist`: private `series_id` selections, separate
  from the existing demo scenario bookmarks.
- `/api/v1/workspace/warnings`: fixture-only queue; `PUT /{warning_id}/review`
  on that route opens the current account's review without duplicating it.
  See the [warning and watchlist contract](../docs/v1_warning_workspace.md).
- `/api/v1/workspace/reviews`: bounded GET and CSRF-protected POST.
- `/api/v1/workspace/reviews/{UUID}`: owner-scoped GET/PATCH.
- `/api/v1/workspace/reviews/{UUID}/report.json` and `/report.csv`: owner-only.

The browser's Warnings and Watchlist views use the private APIs above. They
keep synthetic warnings separate from the current-signal endpoint and link
saved series to History without removing bookmarks for absent observations.

Each review freezes the exact synthetic scenario and content-addressed SQLite
snapshot. Edits require `expected_revision`; stale edits return 409 without
overwriting the newer note. Status transitions and times are recorded; closing
a review is not evidence of model correctness. Closing/dismissing requires a
nonempty analyst note. Events retain status/revision,
not a complete history of previous note text. Foreign IDs return 404, anonymous
requests 401. Export labels remain synthetic and not admitted; CSV neutralizes
formula prefixes. Notes render as text, never as HTML. The browser clears
private state on logout, including same-origin tabs, and stores no private
notes or credentials in localStorage. Watchlist replacement is last-write-wins;
review notes have optimistic concurrency protection.

## Model Boundary

Mila's unchanged temporal core is integrated as optional `arcshift_model` from
`models/validation`. [I05.2 details](../docs/v1_model_integration.md) distinguish
temporal correctness from a trained/admitted model. The legacy trainer and
weights remain unchanged and are never loaded by this API.

- `GET /api/v1/models/task`: the approved business question, independent of
  market snapshot availability. [Task passport](../docs/v1_task_definition.md).
- `GET /api/v1/models/status`: approved RU market-stress onset task with a
  primary 30-calendar-day horizon; frozen but unvalidated measurement, raw-target input
  coverage, calibration/artifact status and current blockers.
- `GET /api/v1/models/measurement`: the versioned [domestic stress definition](../docs/v1_stress_measurement.md)
  and its digest. This endpoint publishes no market data or computed signal.
- `GET /api/v1/signals/current?geography=RU&horizon_days=30`: always null signal
  while admission is missing; unsupported tasks/countries/horizons are distinct.
- The Model view uses `v1-model-readiness.3`, not a fitted-history proxy.
  Legacy 7/90-day candidates and the old future-presence task are unsupported.

API startup and status requests do not import pandas, NumPy, sklearn or joblib.
Optional temporal checks use a separate environment, from the repository root:

```sh
python3 -m venv .venv-validation
.venv-validation/bin/python -m pip install -r requirements-validation.lock
.venv-validation/bin/python -m unittest discover -s tests/model_validation -q
```

The core suite deliberately excludes this optional subdirectory. Current
counts are 183 core/data/API tests and 65 optional validation tests. The temporal
bridge accepts only synthetic standardized components with explicit snapshot,
threshold, horizon and outcome as-of date. It prepares labels/train masks; it
does not implement point-in-time feature construction, a frozen M04 run,
calibration, model fitting, accepted artifacts or a training runner.

`arcshift_model.measurement.measure_stress` implements the frozen domestic
definition on synthetic observations and explicit calendars; `prepared_onset`
passes the matching 30-day labels and policy identity to temporal validation.
It is not imported by the API and does not admit any source, fit or serve a
model. The older five-component `prepare_onset_validation` remains a separate
synthetic prototype with its old target ID; the imported temporal core remains
unchanged.

The offline [forecast candidate handoff](../docs/v1_forecast_candidate.md)
records the first proposed model comparison and its synthetic episode scorecard.

## Saved Reports

The Reports view adapts Nikita's report workflow to the common API and identity
service, not his Streamlit demo accounts or separate SQLite. From a review,
Save Report captures its exact revision/events and the expected market snapshot.
The report is immutable; editing the review later does not alter it.

- `POST /api/v1/workspace/reports`: same-origin/CSRF protected capture with
  expected review revision and expected data snapshot ID; conflicts return 409.
- `GET /api/v1/workspace/reports` and `/{UUID}`: owner-only, bounded listing.
- `GET /api/v1/workspace/reports/{UUID}/export.pdf` (also `.csv` / `.json`):
  authenticated owner check on each download and a separate export rate limit.

All formats use the same frozen payload; PDF/JSON include the analyst note,
CSV contains selected observations/revisions and their report/snapshot IDs.
An explicit empty series list produces a header-only CSV and valid PDF.
All observations are synthetic, not licensed real provider data. Old
`reviews/{UUID}/report.*` endpoints remain dynamic draft exports, not saved
immutable reports. The packaged Liberation Sans font/license supports Cyrillic
without a host font/CDN. Maximum 2000 observation revisions per report. Tests:
168 core + 18 optional temporal. [Integration details](../docs/v1_reports_integration.md).

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
