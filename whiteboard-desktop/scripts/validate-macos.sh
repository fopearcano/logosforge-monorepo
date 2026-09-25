#!/usr/bin/env bash
#
# Build and smoke-test the unsigned LogosForge Whiteboard Intel release and its
# local MCP companion on the same kind of Mac used by the release workflow.
#
# Prerequisites: Intel macOS 12 Monterey or newer, Node.js 22.12+, Python 3.11+,
# npm, Xcode Command Line Tools, curl, file, hdiutil, lsof, and otool. The source
# checkout must contain sibling logosforge/ and whiteboard-desktop/ directories.
#
# Usage from anywhere inside the checkout:
#   bash whiteboard-desktop/scripts/validate-macos.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND="$ROOT/whiteboard-desktop/backend"
DESKTOP="$ROOT/whiteboard-desktop/desktop"
MACHO_SCANNER="$ROOT/whiteboard-desktop/scripts/check-macos-deployment-targets.py"

VALIDATION_DIR=""
BPID=""
APP_PID=""
APP_BACKEND_PID=""
EXPECTED_CORE_VERSION=""

say() { printf '\n\033[1;36m=== %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }

cleanup() {
  result=$?
  trap - EXIT INT TERM
  for pid in "$APP_PID" "$APP_BACKEND_PID" "$BPID"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  case "$VALIDATION_DIR" in
    */logosforge-whiteboard-validate.*)
      rm -rf -- "$VALIDATION_DIR"
      ;;
  esac
  exit "$result"
}
trap cleanup EXIT INT TERM

free_port() {
  python3 -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()'
}

healthy_body() {
  body=$1
  [[ "$body" == *'"status":"ok"'* \
    && "$body" == *'"service":"logosforge-whiteboard-backend"'* \
    && "$body" == *"\"core_version\":\"${EXPECTED_CORE_VERSION}\""* ]]
}

# --- 0. Environment guards -------------------------------------------------
say "0. Validate the release host"
[ "$(uname -s)" = "Darwin" ] || die "this validator must run on macOS"

for command_name in node npm python3 xcode-select curl file hdiutil lsof otool; do
  command -v "$command_name" >/dev/null 2>&1 || die "$command_name is required"
done
[ -x /usr/libexec/PlistBuddy ] || die "/usr/libexec/PlistBuddy is required"

ARCH="$(uname -m)"
[ "$ARCH" = "x86_64" ] || die "this release is Intel-only; expected x86_64, found $ARCH"

MACOS_VERSION="$(sw_vers -productVersion)"
MACOS_MAJOR="${MACOS_VERSION%%.*}"
[ "$MACOS_MAJOR" -ge 12 ] || die "macOS 12 Monterey or newer is required; found $MACOS_VERSION"

node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 12) ? 0 : 1)' \
  || die "Node.js 22.12 or newer is required; found $(node -v)"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python 3.11 or newer is required; found $(python3 --version)"
xcode-select -p >/dev/null 2>&1 || die "Xcode Command Line Tools are missing; run xcode-select --install"

[ -d "$ROOT/logosforge/logosforge" ] || die "shared core not found under $ROOT/logosforge"
[ -f "$BACKEND/logosforge-whiteboard-backend.spec" ] || die "backend spec not found under $BACKEND"
[ -f "$DESKTOP/package-lock.json" ] || die "desktop lockfile not found under $DESKTOP"
[ -f "$MACHO_SCANNER" ] || die "Mach-O deployment-target scanner not found at $MACHO_SCANNER"

printf 'arch: %s | macOS %s | node %s | %s\n' \
  "$ARCH" "$MACOS_VERSION" "$(node -v)" "$(python3 --version)"

VALIDATION_DIR="$(mktemp -d "${TMPDIR:-/tmp}/logosforge-whiteboard-validate.XXXXXX")"
VENV="$VALIDATION_DIR/build-venv"
SMOKE_DATA="$VALIDATION_DIR/backend-smoke"
APP_DATA="$VALIDATION_DIR/packaged-app-data"
APP_PROFILE="$VALIDATION_DIR/electron-profile"
BACKEND_LOG="$VALIDATION_DIR/backend-smoke.log"
APP_LOG="$VALIDATION_DIR/packaged-app.log"
mkdir -p "$SMOKE_DATA" "$APP_DATA" "$APP_PROFILE"

# --- 1. Python environment and backend gates -------------------------------
say "1. Install backend build and test dependencies"
python3 -m venv "$VENV"
PYTHON="$VENV/bin/python"
"$PYTHON" -m pip install --upgrade pip
( cd "$ROOT" && "$PYTHON" -m pip install "./logosforge[export]" -r "$BACKEND/requirements.txt" pytest pyinstaller )
EXPECTED_CORE_VERSION="$("$PYTHON" -c 'import logosforge; print(logosforge.__version__)')"
printf 'expected bundled core: %s\n' "$EXPECTED_CORE_VERSION"

say "2. Run backend tests, byte-compile, and dependency check"
( cd "$ROOT" && "$PYTHON" -m pytest "$BACKEND/tests" -q -p no:cacheprovider )
PYTHONPYCACHEPREFIX="$VALIDATION_DIR/pycache" "$PYTHON" -m compileall -q \
  "$BACKEND/app" \
  "$BACKEND/whiteboard-mcp-entry.py" \
  "$BACKEND/smoke-frozen-mcp.py" \
  "$BACKEND/smoke-packaged-mcp.py" \
  "$MACHO_SCANNER"
"$PYTHON" -m pip check
"$PYTHON" "$MACHO_SCANNER" --self-test

# --- 2. Freeze and smoke-test the native companions ------------------------
say "3. Build the native PyInstaller backend and MCP companion"
rm -rf -- "$BACKEND/dist" "$BACKEND/build"
( cd "$BACKEND" && "$PYTHON" -m PyInstaller logosforge-whiteboard-backend.spec --noconfirm --clean --log-level WARN )
( cd "$BACKEND" && "$PYTHON" -m PyInstaller logosforge-whiteboard-mcp.spec --noconfirm --clean --log-level WARN )

BE="$BACKEND/dist/logosforge-whiteboard-backend/logosforge-whiteboard-backend"
MCP="$BACKEND/dist/logosforge-whiteboard-mcp"
[ -f "$BE" ] || die "frozen backend was not produced at $BE"
[ -x "$BE" ] || die "frozen backend is not executable: $BE"
[ -f "$MCP" ] || die "frozen MCP companion was not produced at $MCP"
[ -x "$MCP" ] || die "frozen MCP companion is not executable: $MCP"
file "$BE"
file "$BE" | grep -Eq 'Mach-O 64-bit executable x86_64' \
  || die "frozen backend is not an Intel x86_64 executable"
file "$MCP"
file "$MCP" | grep -Eq 'Mach-O 64-bit executable x86_64' \
  || die "frozen MCP companion is not an Intel x86_64 executable"

SMOKE_PORT="$(free_port)"
say "4. Smoke-test the frozen backend on dynamic port $SMOKE_PORT"
LOGOSFORGE_DATA_DIR="$SMOKE_DATA" \
LOGOSFORGE_DB_PATH="$SMOKE_DATA/whiteboard.db" \
  "$BE" --host 127.0.0.1 --port "$SMOKE_PORT" >"$BACKEND_LOG" 2>&1 &
BPID=$!

body=""
for attempt in $(seq 1 30); do
  sleep 1
  body="$(curl -fsS --max-time 2 "http://127.0.0.1:$SMOKE_PORT/health" 2>/dev/null || true)"
  if healthy_body "$body"; then
    printf 'healthy after %ss: %s\n' "$attempt" "$body"
    break
  fi
done

if ! healthy_body "$body"; then
  tail -n 80 "$BACKEND_LOG" >&2 || true
  die "frozen backend failed its identity/core health check"
fi
kill "$BPID" 2>/dev/null || true
wait "$BPID" 2>/dev/null || true
BPID=""

say "5. Smoke-test the frozen MCP bridge"
"$PYTHON" "$BACKEND/smoke-frozen-mcp.py" "$BE" "$MCP"

# --- 3. Desktop dependency and build gates ---------------------------------
say "6. Install desktop dependencies and verify Electron toolchain"
( cd "$DESKTOP" && npm ci )
ELECTRON_VERSION="$(cd "$DESKTOP" && node -p 'require("./node_modules/electron/package.json").version')"
BUILDER_VERSION="$(cd "$DESKTOP" && node -p 'require("./node_modules/electron-builder/package.json").version')"
case "$ELECTRON_VERSION" in 43.*) ;; *) die "expected Electron 43.x, found $ELECTRON_VERSION" ;; esac
case "$BUILDER_VERSION" in 26.*) ;; *) die "expected electron-builder 26.x, found $BUILDER_VERSION" ;; esac
printf 'Electron %s | electron-builder %s\n' "$ELECTRON_VERSION" "$BUILDER_VERSION"

say "7. Run desktop tests, build, and moderate-or-higher audit gate"
( cd "$DESKTOP" && npm test && npm run build && npm audit --audit-level=moderate )

# --- 4. Package and inspect the app ----------------------------------------
PACKAGE_VERSION="$(cd "$DESKTOP" && node -p 'require("./package.json").version')"
DMG="$DESKTOP/release/LogosForge Whiteboard-${PACKAGE_VERSION}-x64.dmg"
APP="$DESKTOP/release/mac/LogosForge Whiteboard.app"
APP_BE="$APP/Contents/Resources/backend/logosforge-whiteboard-backend"
APP_MCP="$APP/Contents/Resources/mcp/logosforge-whiteboard-mcp"
APP_EXE="$APP/Contents/MacOS/LogosForge Whiteboard"

say "8. Build the unsigned Intel DMG"
rm -rf -- "$DESKTOP/release/mac"
rm -f -- "$DMG"
( cd "$DESKTOP" && CSC_IDENTITY_AUTO_DISCOVERY=false npm run dist:mac )

[ -f "$DMG" ] || die "DMG was not produced at $DMG"
[ -d "$APP" ] || die "packaged app was not produced at $APP"
[ -f "$APP_BE" ] || die "bundled backend is missing from $APP"
[ -x "$APP_BE" ] || die "bundled backend lost its executable bit: $APP_BE"
[ -f "$APP_MCP" ] || die "bundled MCP companion is missing from $APP"
[ -x "$APP_MCP" ] || die "bundled MCP companion lost its executable bit: $APP_MCP"
[ -x "$APP_EXE" ] || die "packaged Electron executable is missing: $APP_EXE"
file "$APP_BE"
file "$APP_BE" | grep -Eq 'Mach-O 64-bit executable x86_64' \
  || die "bundled backend is not Intel x86_64"
file "$APP_MCP"
file "$APP_MCP" | grep -Eq 'Mach-O 64-bit executable x86_64' \
  || die "bundled MCP companion is not Intel x86_64"
file "$APP_EXE"
file "$APP_EXE" | grep -Eq 'Mach-O 64-bit executable x86_64' \
  || die "packaged Electron executable is not Intel x86_64"

MINIMUM_SYSTEM_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' "$APP/Contents/Info.plist")"
[ "$MINIMUM_SYSTEM_VERSION" = "12.0.0" ] \
  || die "expected LSMinimumSystemVersion 12.0.0, found $MINIMUM_SYSTEM_VERSION"

PACKAGED_ELECTRON_VERSION="$(ELECTRON_RUN_AS_NODE=1 "$APP_EXE" -p 'process.versions.electron')"
case "$PACKAGED_ELECTRON_VERSION" in
  43.*) ;;
  *) die "expected packaged Electron 43.x, found $PACKAGED_ELECTRON_VERSION" ;;
esac
printf 'packaged Electron %s | LSMinimumSystemVersion %s\n' \
  "$PACKAGED_ELECTRON_VERSION" "$MINIMUM_SYSTEM_VERSION"

say "9. Scan packaged Mach-O deployment targets"
"$PYTHON" "$MACHO_SCANNER" "$APP" --maximum 12.0.0

# --- 5. Launch and exercise the actual packaged app ------------------------
APP_PORT="$(free_port)"
lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1 \
  && die "dynamic app port $APP_PORT became occupied before launch"

say "10. Launch the packaged app with isolated state on dynamic port $APP_PORT"
LOGOSFORGE_HOST=127.0.0.1 \
LOGOSFORGE_PORT="$APP_PORT" \
LOGOSFORGE_DATA_DIR="$APP_DATA" \
LOGOSFORGE_DB_PATH="$APP_DATA/whiteboard.db" \
  "$APP_EXE" --user-data-dir="$APP_PROFILE" >"$APP_LOG" 2>&1 &
APP_PID=$!

body=""
for attempt in $(seq 1 45); do
  sleep 1
  body="$(curl -fsS --max-time 2 "http://127.0.0.1:$APP_PORT/health" 2>/dev/null || true)"
  if healthy_body "$body"; then
    printf 'packaged backend healthy after %ss: %s\n' "$attempt" "$body"
    break
  fi
done

if ! healthy_body "$body"; then
  tail -n 120 "$APP_LOG" >&2 || true
  die "the packaged app did not launch the expected core $EXPECTED_CORE_VERSION backend"
fi

APP_BACKEND_PID="$(lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
[ -n "$APP_BACKEND_PID" ] || die "health responded but the backend listener PID could not be identified"

kill "$APP_PID" 2>/dev/null || true
wait "$APP_PID" 2>/dev/null || true
APP_PID=""
sleep 2
if kill -0 "$APP_BACKEND_PID" 2>/dev/null; then
  kill "$APP_BACKEND_PID" 2>/dev/null || true
  wait "$APP_BACKEND_PID" 2>/dev/null || true
fi
APP_BACKEND_PID=""

say "11. Exercise the packaged MCP bridge from the DMG"
"$PYTHON" "$BACKEND/smoke-packaged-mcp.py" "$DMG" --timeout 120

printf '\n\033[1;32mPASS — backend and MCP tests, freezes, smokes, desktop gates, Monterey metadata, Mach-O targets, DMG packaging, packaged-app health, and packaged MCP bridge all passed.\033[0m\n'
printf 'Installer: %s\n' "$DMG"

cat <<EOF

To validate the downloaded unsigned-DMG experience on macOS 12+:
  1. Mount "$DMG" and copy LogosForge Whiteboard.app to /Applications.
  2. Clear quarantine recursively so the bundled backend is included:
       xattr -cr "/Applications/LogosForge Whiteboard.app"
  3. Open the app normally and repeat the persistence/import/export checks in
     whiteboard-desktop/RELEASING.md.

The build is unsigned and unnotarized; Gatekeeper warnings are expected.
EOF
