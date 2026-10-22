#!/usr/bin/env bash
# ===========================================================================
#  Chaudhary Type House & Property Advisors
#  ONE-COMMAND launcher for macOS / Linux - installs everything FREE, then runs.
#  Zero paid APIs. Zero cost. Docker NOT required.
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo
echo " ============================================================"
echo "   CHAUDHARY TYPE HOUSE & PROPERTY ADVISORS"
echo "   Near Baldia Chowk, City Chishtian"
echo "   Owner: Chaudhary Muhammad Sanaullah - 0308-3027589"
echo "   FREE Registry Kharcha Calculator: https://chtype.online"
echo " ============================================================"
echo

# ---------- 1. Locate Python ----------
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)' >/dev/null 2>&1; then
      PY="$c"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "[X] Python 3.9+ nahi mila."
  echo "    macOS : brew install python    (ya python.org se install karein)"
  echo "    Ubuntu: sudo apt install python3 python3-venv"
  exit 1
fi
echo "[1/5] Python mil gaya: $($PY --version)"

# ---------- 2. Virtual environment ----------
if [ ! -f ".venv/bin/python" ]; then
  echo "[2/5] Virtual environment bana rahe hain..."
  "$PY" -m venv .venv
fi
VPY=".venv/bin/python"
"$VPY" -m pip install --upgrade pip --quiet
echo "[2/5] Virtual environment ready."

# ---------- 3. FREE dependencies ----------
echo "[3/5] FREE libraries install ho rahi hain..."
"$VPY" -m pip install -r requirements.txt --quiet
"$VPY" -c 'import fastapi, PIL, uvicorn' >/dev/null 2>&1 || {
  echo "[X] Core packages install nahi hue. Internet check karein."; exit 1; }

# ---------- 4. Playwright (free, one time) ----------
echo "[4/5] Playwright Chromium install ho raha hai (FREE, ek baar)..."
"$VPY" -m playwright install chromium || {
  echo "[!] Chromium install nahi hua - browser agents ke liye dobara chala dein."; }
"$VPY" -m playwright install-deps chromium 2>/dev/null || true

# ---------- 5. Launch ----------
echo "[5/5] System start ho raha hai..."
echo
echo "  Website  : http://127.0.0.1:8000/"
echo "  Dashboard: http://127.0.0.1:8000/dashboard"
echo
exec "$VPY" app.py