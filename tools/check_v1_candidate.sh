#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    printf 'Usage: bash tools/check_v1_candidate.sh <commit-or-ref>\n' >&2
    exit 2
fi

repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
revision=$(git -C "$repo" rev-parse --verify --end-of-options "$1^{commit}")
work=$(mktemp -d "${TMPDIR:-/tmp}/arcshift-v1-check.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
unset PYTHONPATH
export PYTHONNOUSERSITE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
python=${ARCSHIFT_PYTHON:-python3.14}

printf 'Verifying commit %s\n' "$revision"
mkdir "$work/source" "$work/smoke"
git -C "$repo" archive "$revision" | tar -xf - -C "$work/source"
cd "$work/source"
"$python" -m venv .venv-v1
runtime="$work/source/.venv-v1/bin/python"
"$runtime" -m pip install -r requirements-v1.lock
"$runtime" -m pip install --no-build-isolation --no-deps -e .
"$runtime" -m pip check
"$runtime" -m unittest discover -s tests -q

"$python" -m venv .venv-validation
validation="$work/source/.venv-validation/bin/python"
"$validation" -m pip install -r requirements-validation.lock
"$validation" -m pip check
"$validation" -m unittest discover -s tests/model_validation -q

case ${ARCSHIFT_RUN_BROWSER:-0} in
    1) node tools/smoke_v1_workbench.cjs ;;
    0) printf 'Browser smoke skipped; rerun with ARCSHIFT_RUN_BROWSER=1.\n' ;;
    *) printf 'ARCSHIFT_RUN_BROWSER must be 0 or 1.\n' >&2; exit 2 ;;
esac

"$runtime" -m pip wheel --no-build-isolation --no-deps --wheel-dir "$work/wheels" .
"$python" -m venv "$work/installed"
installed="$work/installed/bin/python"
"$installed" -m pip install -r requirements-v1.lock "$work"/wheels/*.whl
"$installed" -m pip check
cp tools/smoke_v1_backend.py tools/smoke_v1_auth.py "$work/smoke"
cd "$work/smoke"
"$installed" -m arcshift_v1.dev_outbox --help >/dev/null
"$installed" smoke_v1_backend.py
"$installed" smoke_v1_auth.py
printf 'Candidate checks passed for %s\n' "$revision"
