# V1 Synthetic Warning Workspace

Status: API and browser workflow verified locally on `v1/integration-yaroslav`,
based on `3c35411`. Candidate contract, not a release gate or model admission.

## Contract For UI

Paths below are relative to `/api/v1/workspace`. Use the existing local session
cookie. For `PUT`, send the same-origin header and `X-CSRF-Token` as for reviews.

| Method and path | Request and response |
| --- | --- |
| `GET /warnings` | `v1-local-warnings.1` envelope with `warnings`, newest first. Two synthetic events. Each item has `warning_id`, `event_key`, `policy_version`, `occurred_at`, `fixture_snapshot_id`, `data_snapshot_id`, `validity_status=historical_demo`, and the current user's `review_id` and `review_status`. |
| `PUT /warnings/{warning_id}/review` | No body. Returns `200` and a `ReviewView` with a `warning` reference. First call acknowledges and opens a review. Repeated calls return that user's existing review as-is, including its latest status and revision. |
| `GET /series-watchlist` | Owner-scoped `series_ids`, sorted; `[]` if empty. |
| `PUT /series-watchlist` | Replace with `{"series_ids":["ru.fx.cbr.usd_rub.official"]}`; use `[]` to clear. Unknown/duplicate IDs and extra fields are rejected (`422`) before writing. Replacement is last-write-wins. |

`new` means no personal review and `review_id=null`. Do not infer a current
forecast, severity, or calibration from a test warning. The two events are
seeded independently of model output and share the example scenario as review
context; the score inside that legacy scenario did not produce the warnings.
The current-signal endpoint is unchanged. The queue omits notes and other
users' review IDs. Opening a warning is an explicit user action, not part of
polling or rendering. Use existing `GET/PATCH /reviews/{review_id}` to edit;
the same revision checks, status transitions, and closing-note rules apply.

Display names/history for the watchlist come from `/api/v1/market/series` and
its history endpoint. Keep stored IDs if a supported series is temporarily
missing from the active snapshot. The older `/watchlist` with `scenario_ids`
is a separate demo endpoint. The new list does not migrate those bookmarks.

When saving a warning-linked report, send the review's `revision` and
`warning.data_snapshot_id` as `expected_revision` and `expected_data_snapshot_id`.
Do not substitute the currently active market snapshot. If no series selection
is required, omit `series_ids`; otherwise select IDs from the pinned snapshot.
An unlinked review still uses the active snapshot. Wrong versions return `409`;
foreign reviews/reports and unknown warning IDs return `404`; anonymous access
returns `401`. The JSON and PDF identify the test warning. The observation CSV
keeps its existing report and market snapshot IDs and format.

## Change Journal

- Migration `006_local_warning_workspace.sql` adds system warnings and a
  per-account series watchlist without rewriting existing tables' data. A
  unique event/policy pair identifies the warning; a partial unique index
  allows one review per account and warning. Existing review payloads omit
  the new `warning` field when not linked.
- Startup inserts missing fixture events in one SQLite write transaction and
  pins them to the synthetic scenario and market snapshots available at seed
  time. Subsequent startups and read requests do not duplicate or retarget
  them. There is no user-facing write to system warnings.
- The existing review and report screens render warning provenance and use
  the pinned market snapshot for capture.
- The browser now opens the private warning queue and series watchlist directly.
  New warnings open a review explicitly; existing reviews reopen without a
  write. The list accepts additions from the catalog or the history screen,
  and links available entries to their exact series history. Legacy scenario
  bookmarks remain available through the old API, not mixed into this view.
- The two views distinguish signed-out, loading, error and empty states.
  Saved IDs remain visible when missing from the active catalog. The history
  screen displays rows only when the response agrees with the catalog snapshot
  and the selected series. Account changes clear both views and discard late
  responses from the previous account state.
- Refresh does not replace a review form if the analyst started typing while
  the requests were in flight. Leaving a draft still asks for confirmation.
- Local test accounts and temporary SQLite only. No provider call, real
  email, historical download, fit, release gate change, or deployment.

## Verification

- `tests/test_v1_warning_workspace.py`: two-account review/report isolation,
  concurrent acknowledgement, CSRF, no writes on refresh, watchlist validation
  and persistence, changed active values, and pinned reports after restart.
- `tests/test_v1_storage.py`: migration from schema 005 preserves the existing
  review, status event, scenario bookmark and saved report payload.
- `.venv-v1/bin/python -m unittest discover -s tests -q`: 177 passed.
- `tools/smoke_v1_workbench.cjs`: local Chrome at 1440/390/320 px; queue to
  review and report, keyboard actions, queue retry after a simulated `503`,
  two isolated watchlists, add/remove, missing catalog row, mixed snapshot
  rejection, draft preservation during refresh, reload and cross-tab logout.
  No unexpected browser errors or
  external requests. The smoke uses a temporary server and SQLite database.

Next: review the contract and workflow with UI/model owners and re-run
acceptance on a shared checkpoint. Synthetic IDs and the
seed policy are not a production deduplication or warning threshold decision.
