#!/usr/bin/env bash
#
# validate-macos.sh — build + smoke-test the LogosForge Whiteboard macOS (Intel x64)
# release LOCALLY on the target Mac, mirroring the GitHub Actions workflow
# (.github/workflows/release-whiteboard-macos.yml). This is the way to validate
# the unsigned Intel DMG on a Monterey (incl. OCLP) Intel Mac.
#
#   bash whiteboard-desktop/scripts/validate-macos.sh
#
# It freezes the backend (PyInstaller), packages the DMG (electron-builder),
# launches the .app, and confirms the bundled backend answers /health on :8777.
#
# Prereqs on the Mac: Node 20, Python 3.11, Xcode Command Line Tools
# (`xcode-select --install`), and the monorepo source — logosforge/ +
# whiteboard-desktop/ as SIBLINGS, copied WITHOUT any node_modules/.venv/dist/
# build/release (those are Windows/platform-specific). Intel only (x86_64).
#
# A locally-built .app is NOT quarantined, so it launches with no Gatekeeper
# prompt. To instead validate the DOWNLOADED-DMG experience a tester hits, see
# the "simulate a download" notes printed at the end.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"          # monorepo root (…/Logosforge Alphatest)
BACKEND="$ROOT/whiteboard-desktop/backend"
DESKTOP="$ROOT/whiteboard-desktop/desktop"
VENV="$ROOT/build-venv"
SMOKE_PORT=8799   # isolated smoke port (matches CI)
APP_PORT=8777     # the app's real backend port (backend-entry.py default)

say() { printf '\n\033[1;36m=== %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }

# --- 0. Environment guards -------------------------------------------------
say "0. Environment"
[ "$(uname -s)" = "Darwin" ] || die "not macOS"
ARCH="$(uname -m)"
echo "arch: $ARCH | node $(node -v 2>&1) | $(python3 --version 2>&1) | $(sw_vers -productName) $(sw_vers -productVersion)"
[ "$ARCH" = "x86_64" ] || echo "WARNING: arch is '$ARCH', not x86_64 — this DMG is Intel-only. On Apple Silicon it runs under Rosetta and an unsigned Mach-O can be Killed:9."
command -v node >/dev/null   || die "node not found (install Node 20)"
command -v python3 >/dev/null || die "python3 not found (install Python 3.11)"
[ -d "$ROOT/logosforge" ] && [ -d "$ROOT/whiteboard-desktop" ] || die "expected siblings logosforge/ + whiteboard-desktop/ under $ROOT"

# --- 1. Clean any copied (Windows) backend build artifact ------------------
say "1. Remove stale backend build artifacts (a copied Windows PyInstaller tree would mismatch)"
rm -rf "$BACKEND/dist" "$BACKEND/build"

# --- 2. Build venv + deps (mirrors CI) -------------------------------------
say "2. Create build venv + install logosforge[export] + wrapper deps + pyinstaller"
rm -rf "$VENV"
python3 -m venv "$VENV" || die "venv create failed"
"$VENV/bin/python" -m pip install --upgrade pip -q || die "pip upgrade failed"
( cd "$ROOT" && "$VENV/bin/python" -m pip install "./logosforge[export]" fastapi "uvicorn[standard]" httpx pyinstaller ) \
  || die "pip install failed"

# --- 3. Freeze the backend -------------------------------------------------
say "3. PyInstaller freeze (cwd = backend/, the spec uses a relative entry)"
( cd "$BACKEND" && "$VENV/bin/python" -m PyInstaller logosforge-whiteboard-backend.spec --noconfirm --clean --log-level WARN ) \
  || die "PyInstaller failed"
BE="$BACKEND/dist/logosforge-whiteboard-backend/logosforge-whiteboard-backend"
[ -f "$BE" ] || die "frozen backend not produced at $BE"
echo "frozen: $(file "$BE")"
file "$BE" | grep -q "x86_64" || echo "WARNING: frozen backend is not x86_64"
[ -x "$BE" ] || die "frozen backend is not executable"

# --- 4. Smoke-test the frozen backend (BODY-checked, not just HTTP 200) -----
say "4. Smoke-test frozen backend on :$SMOKE_PORT (require {\"status\":\"ok\"})"
LOGOSFORGE_DB_PATH="$ROOT/.mac-smoke.db" "$BE" --host 127.0.0.1 --port "$SMOKE_PORT" &
BPID=$!
ok=""
for i in $(seq 1 30); do
  sleep 1
  body="$(curl -s --max-time 2 "http://127.0.0.1:$SMOKE_PORT/health" || true)"
  case "$body" in *'"status":"ok"'*) ok="yes"; echo "healthy after ${i}s: $body"; break;; esac
done
kill "$BPID" 2>/dev/null || true
rm -f "$ROOT/.mac-smoke.db"
[ -n "$ok" ] || die "frozen backend never returned status:ok — run it in the foreground to read the traceback: \"$BE\" --host 127.0.0.1 --port $SMOKE_PORT"

# --- 5/6. Install desktop deps + package the unsigned DMG ------------------
say "5. npm ci (electron-builder 25 + electron 31)"
( cd "$DESKTOP" && npm ci ) || die "npm ci failed"
say "6. Build + package unsigned DMG (npm run dist:mac)"
( cd "$DESKTOP" && CSC_IDENTITY_AUTO_DISCOVERY=false npm run dist:mac ) || die "electron-builder failed"

DMG="$(ls "$DESKTOP"/release/*.dmg 2>/dev/null | head -1)"
APP="$DESKTOP/release/mac/LogosForge Whiteboard.app"
[ -n "$DMG" ] && [ -d "$APP" ] || die "DMG/.app not produced under $DESKTOP/release"

# --- 7. Verify the bundled sidecar inside the .app -------------------------
say "7. Verify the bundled backend inside the .app (arch + exec bit)"
APP_BE="$APP/Contents/Resources/backend/logosforge-whiteboard-backend"
[ -f "$APP_BE" ] || die "bundled backend missing from the .app at $APP_BE"
ls -l "$APP_BE"; file "$APP_BE"
[ -x "$APP_BE" ] || { echo "exec bit missing — restoring"; chmod +x "$APP_BE"; }

# --- 8. Launch the locally-built app + verify the backend on :8777 ---------
say "8. Launch the app (locally built => not quarantined => no Gatekeeper prompt)"
if lsof -i ":$APP_PORT" >/dev/null 2>&1; then
  echo "WARNING: something already listens on :$APP_PORT — kill it (lsof -i :$APP_PORT) or the app will attach to it and mask a broken bundle."
fi
open "$APP"
ok=""
for i in $(seq 1 30); do
  sleep 1
  body="$(curl -s --max-time 2 "http://127.0.0.1:$APP_PORT/health" || true)"
  case "$body" in *'"status":"ok"'*) ok="yes"; echo "app's bundled backend healthy after ${i}s: $body"; break;; esac
done

echo
if [ -n "$ok" ]; then
  printf '\033[1;32mPASS — the packaged app launched and its bundled backend is live on :%s.\033[0m\n' "$APP_PORT"
else
  printf '\033[1;33mApp launched but :%s never returned status:ok. Triage:\033[0m\n' "$APP_PORT"
  echo "  • blank/black WINDOW on a non-Metal OCLP GPU → quit, relaunch: open \"$APP\" --args --disable-gpu"
  echo "  • 'spawn EACCES'  → chmod +x \"$APP_BE\" ; relaunch"
  echo "  • read the error  → run the bundled binary directly: \"$APP_BE\" --host 127.0.0.1 --port $APP_PORT"
fi
echo
echo "Installer (share/test the downloaded-DMG path with this): $DMG"
cat <<EOF

To validate the END-USER (downloaded) experience — Monterey quarantines nested
binaries and only clears the .app ROOT on first run, so the bundled backend
stays blocked unless you clear quarantine RECURSIVELY:
    hdiutil attach "$DMG"
    cp -R "/Volumes/LogosForge Whiteboard/LogosForge Whiteboard.app" /Applications/
    hdiutil detach "/Volumes/LogosForge Whiteboard"
    xattr -cr "/Applications/LogosForge Whiteboard.app"   # RECURSIVE — required on Monterey
    open "/Applications/LogosForge Whiteboard.app"
(The non-recursive 'xattr -d com.apple.quarantine' leaves the sidecar quarantined.)
EOF
