#!/usr/bin/env bash
# One-shot setup for EIRA on a fresh machine (written for macOS, works on Linux).
# Idempotent: safe to run repeatedly. Re-running skips what is already done.
#
#   bash scripts/setup_mac.sh
#
# It never touches .env, so your keys are never at risk from a re-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV="${REPO_ROOT}/.venv"
PY_MIN_MAJOR=3
PY_MIN_MINOR=10

say()  { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[0;32mok\033[0m  %s\n' "$*"; }
warn() { printf '    \033[0;33m!\033[0m   %s\n' "$*"; }

# ---------------------------------------------------------------- interpreter
say "Checking Python"
PYBIN=""
for cand in python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver="$("$cand" -c 'import sys; print("%d %d" % sys.version_info[:2])')"
    maj="${ver% *}"; min="${ver#* }"
    if [ "$maj" -gt "$PY_MIN_MAJOR" ] || { [ "$maj" -eq "$PY_MIN_MAJOR" ] && [ "$min" -ge "$PY_MIN_MINOR" ]; }; then
      PYBIN="$cand"; break
    fi
  fi
done
[ -n "$PYBIN" ] || { echo "need Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR}+ on PATH"; exit 1; }
ok "$PYBIN ($("$PYBIN" --version 2>&1))"

# --------------------------------------------------------------------- venv
say "Virtual environment"
if [ -x "${VENV}/bin/python" ]; then
  ok "reusing ${VENV}"
else
  "$PYBIN" -m venv "$VENV"
  ok "created ${VENV}"
fi
VPY="${VENV}/bin/python"
"$VPY" -m pip install --quiet --upgrade pip
ok "pip up to date"

# ------------------------------------------------------------------ packages
say "Installing dependencies (first run pulls torch, this takes a few minutes)"
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  ok "Apple Silicon: default torch wheel is correct"
else
  "$VPY" -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu || \
    warn "CPU torch index failed, falling back to the default wheel"
fi
"$VPY" -m pip install --quiet -r requirements.txt
ok "requirements installed"

# ---------------------------------------------------------- model + demo data
say "Caching the speech-emotion model (skipped if already cached)"
if "$VPY" scripts/prefetch_models.py; then
  ok "model ready"
else
  warn "model prefetch failed. EIRA still runs; only POST /emotion is affected."
fi

say "Generating synthetic wearable data"
"$VPY" scripts/gen_wearables.py
ok "data/wearable_sim.json written"

say "Seeding memory"
if [ -f .env ] && grep -q '^QDRANT_URL=..*' .env 2>/dev/null; then
  if "$VPY" scripts/seed_data.py; then
    ok "Qdrant seeded"
  else
    warn "seeding failed. Check QDRANT_URL and QDRANT_API_KEY in .env, then re-run:"
    warn "  ${VENV}/bin/python scripts/seed_data.py"
  fi
else
  warn "no .env with QDRANT_URL yet, so seeding was skipped (expected on a fresh clone)"
fi

# ----------------------------------------------------------------- next steps
cat <<EOF

$(printf '\033[1;35m==> Setup complete\033[0m')

now copy .env into repo root, then:
  source ${VENV}/bin/activate
  python scripts/seed_data.py      # if it was skipped above
  uvicorn main:app --app-dir backend --port 8000

then open http://127.0.0.1:8000 in Chrome.

verify anything is wrong with:
  python scripts/test_rime.py      # voice
  python scripts/test_qdrant.py    # memory + tenant isolation
  python scripts/eval_harness.py   # full regression, needs the server running
EOF
