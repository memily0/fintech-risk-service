# Implementation Log

## [2026-06-03] setup | repository and branch

- Cloned backend repository `memily0/fintech-risk-service` into the local workspace.
- Created working branch `feature/crisis-model-mvp`.
- Cloned reference repository `bank-of-england/MachineLearningCrisisPrediction`.
- Cloned workflow gist `442a6bf555914893e9891c11519de94f`.
- No backend code changes were made in this step.

## [2026-06-03] analysis | first implementation direction

- Local product documents define IVR as an early-warning platform and risk navigator.
- MVP focus is financial crisis probability in Russia based on external market and macrofinancial data.
- Current backend already has a daily market dataset and Streamlit dashboard.
- Current backend has no trained prediction model, no explicit target, and no model validation pipeline.
- Bank of England reference repo is useful for methodology: pre-crisis target window, post-crisis exclusion, forecasting splits, baseline models, and Shapley-style explanations.
- Direct code reuse from the Bank of England repo is not recommended for MVP because it is old research code for annual panel data, not a modern production module for daily Russian market data.

## [2026-06-04] implementation | MVP-1.0 baseline model

- Added `scripts/train_crisis_model.py`.
- Added reproducible model artifacts:
  - `data/model_predictions.csv`;
  - `data/model_metrics.json`;
  - `models/artifacts/crisis_logreg_7d.joblib`;
  - `models/artifacts/crisis_logreg_30d.joblib`;
  - `models/artifacts/crisis_logreg_90d.joblib`.
- Added `scikit-learn` and `joblib` to `requirements.txt`.
- Integrated model output into `app/dashboard.py`:
  - top-level financial stress forecast block;
  - horizon selector for 7/30/90 days;
  - model forecast tab;
  - latest top drivers;
  - walk-forward metrics table.
- Model design:
  - target is a future stress event from a trailing z-score composite stress index;
  - stress threshold is `1.0`;
  - features use trailing z-scores, lagged returns/deltas, and missing flags;
  - classifier is balanced logistic regression with `C=0.01`.
- Verification:
  - `.venv/bin/python scripts/train_crisis_model.py` completed successfully.
  - `python3 -m py_compile app/dashboard.py scripts/train_crisis_model.py scripts/build_final_dataset.py` completed successfully.
  - Dashboard module smoke test completed successfully.
  - Streamlit server started successfully outside the sandbox and returned HTTP 200 on `http://localhost:8501`.
  - In-app browser verified the top-level forecast block and model tab presence.

## [2026-06-04] environment | temporary public demo access

- Started a fresh Streamlit server on `http://localhost:8502` because port `8501` had an old listener that did not respond to local HTTP checks.
- Installed `cloudflared` through Homebrew to test Cloudflare Tunnel for temporary public access.
- Cloudflare quick tunnel was not usable in this local network because `cloudflared` could not resolve Cloudflare tunnel SRV records through the local DNS resolver at `[::1]:53`, resulting in HTTP `530` from the generated public URL.
- Started `localtunnel` against Streamlit port `8502`.
- Verified that the generated public URL returned HTTP `200` and served the Streamlit app.
- This public demo link is temporary and depends on both the local Streamlit process and the local tunnel process staying alive.

## [2026-06-04] environment | public demo access disabled

- Stopped the temporary `localtunnel` process.
- Verified that no `localtunnel` or `cloudflared` processes remained active.
- Uninstalled `cloudflared`, because public tunnel access is postponed until a deliberate deploy step.
- Kept the Streamlit dashboard available locally on `http://localhost:8502`.

## [2026-06-04] release | branch publication preparation

- Re-ran Python compile checks for `app/dashboard.py`, `scripts/train_crisis_model.py`, and `scripts/build_final_dataset.py`.
- Re-ran `scripts/train_crisis_model.py` to regenerate model predictions, metrics, and sklearn artifacts before commit.
- Prepared branch `feature/crisis-model-mvp` for publication to `origin` (`memily0/fintech-risk-service.git`).

## [2026-06-04] release | branch published

- Committed MVP-1.0 model and dashboard integration as `e768d23` with message `Add MVP crisis prediction model`.
- Pushed branch `feature/crisis-model-mvp` to `origin`.

## [2026-06-05] fix | sidebar restore control

- Investigated a Streamlit UI issue where the sidebar could not be restored after being collapsed.
- Root cause: custom dashboard CSS hid the full Streamlit toolbar via `[data-testid="stToolbar"] { display: none; }`.
- Changed the CSS to hide only non-essential Streamlit header buttons (`Deploy` and main menu), leaving toolbar/sidebar controls available.
- Made the sidebar collapse control permanently visible because Streamlit renders it as hover-only by default.

## [2026-06-08] data | historical dataset extension

- Changed the default dataset start date from `2014-01-01` to `2003-01-01`.
- Reworked the CBR monetary policy rate loader:
  - uses the official CBR monetary policy rates table;
  - uses `Key rate` when available;
  - falls back to `Refinancing Rate` before key-rate history starts.
- Rebuilt `data/final_dataset.csv` for `2003-01-01` through `2026-06-06`.
- Rebuilt model predictions, metrics, and sklearn artifacts on the extended dataset.
- Source coverage after rebuild:
  - USD/RUB and EUR/RUB: from `2003-01-01`;
  - gold, VIX, S&P500: from `2003-01-02`;
  - IMOEX: from `2003-01-04`;
  - Brent: from `2007-07-30`;
  - OFZ curves: from `2014-01-06` using existing local MOEX files;
  - inflation: from `2014-02-01` using the existing local monthly file.
- No proxy was added for OFZ or inflation before their available source history.
- Latest model metrics after rebuild:
  - 7d latest probability `0.074`, regime `Normal`, mean ROC-AUC `0.881`;
  - 30d latest probability `0.231`, regime `Watch`, mean ROC-AUC `0.784`;
  - 90d latest probability `0.076`, regime `Normal`, mean ROC-AUC `0.642`.
