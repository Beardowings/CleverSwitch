#!/bin/bash
set -euo pipefail

# Build the CleverSwitch macOS release archive: CleverSwitch.app (menu bar app, no Dock icon)
# packed with the docs and the config example.
# Output: dist/cleverswitch_macOS.tar.gz

BUNDLE_NAME="CleverSwitch"
BUNDLE_ID="io.github.beardowings.cleverswitch"
ARCHIVE="cleverswitch_macOS"

# ── Helpers ──────────────────────────────────────────────────────────

info()  { printf "\033[1;34m==> %s\033[0m\n" "$*"; }
ok()    { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m==> %s\033[0m\n" "$*"; }
error() { printf "\033[1;31m==> %s\033[0m\n" "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

export MACOSX_DEPLOYMENT_TARGET=14.0

# ── Step 1: Runtime dependencies ─────────────────────────────────────
# PyInstaller only bundles what is importable at build time — it does NOT
# read pyproject.toml. A missing runtime dep is silently dropped (build-log
# warning only) and the binary then crashes at launch with ModuleNotFoundError.
# This is exactly how the broken v1.2.5 release shipped. `pip install .` pulls
# in pyyaml plus the macOS-only bleak + pyobjc.

info "Installing runtime dependencies..."
pip install .
pip install pyinstaller

info "Sanity-checking imports..."
python -c "import yaml; print('pyyaml ok')" || error "pyyaml not importable — aborting before a broken build."

# ── Step 2: PyInstaller ──────────────────────────────────────────────
# libhidapi is loaded at runtime via ctypes.CDLL, which PyInstaller cannot
# detect — it must be bundled explicitly or the binary only works on machines
# that already have `brew install hidapi`. transport.py looks for it in _MEIPASS.
# --hidden-import yaml is a safety net.

HIDAPI_DYLIB="$(brew --prefix hidapi 2>/dev/null || true)/lib/libhidapi.dylib"
if [ ! -f "$HIDAPI_DYLIB" ]; then
    info "Homebrew hidapi not found — building it from source."
    "$ROOT_DIR/scripts/build_hidapi.sh"
    HIDAPI_DYLIB="$ROOT_DIR/build/hidapi/install/lib/libhidapi.dylib"
    [ -f "$HIDAPI_DYLIB" ] || error "hidapi source build did not produce $HIDAPI_DYLIB."
fi
info "Bundling $HIDAPI_DYLIB"

info "Building CleverSwitch.app with PyInstaller..."
# --windowed builds an app bundle: the menu bar icon needs one, and macOS then ties the Input
# Monitoring and Bluetooth permissions to CleverSwitch itself instead of to Terminal.
# pystray picks its backend at runtime, so the macOS one is named explicitly.
rm -rf "dist/$BUNDLE_NAME.app"
pyinstaller --noconfirm --windowed --name "$BUNDLE_NAME" --osx-bundle-identifier "$BUNDLE_ID" \
    --paths src --hidden-import yaml --hidden-import pystray._darwin --copy-metadata cleverswitch \
    --add-binary "$HIDAPI_DYLIB:." \
    src/cleverswitch/__main__.py

APP="dist/$BUNDLE_NAME.app"
PLIST="$APP/Contents/Info.plist"
VERSION="$(python -c 'from importlib.metadata import version; print(version("cleverswitch"))')"
# LSUIElement: menu bar only, no Dock icon. Without the Bluetooth usage text macOS kills the app the
# moment CoreBluetooth is touched (the macOS Bluetooth path reads the keyboard over GATT).
plutil -replace LSUIElement -bool true "$PLIST"
plutil -replace NSBluetoothAlwaysUsageDescription \
    -string "CleverSwitch talks to your Logitech keyboard and mouse over Bluetooth to switch them between computers." "$PLIST"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
# Editing Info.plist breaks PyInstaller's ad-hoc signature; Apple silicon refuses unsigned code.
codesign --force --deep --sign - "$APP"

# ── Step 3: Smoke-test ───────────────────────────────────────────────
# Catch a dropped dependency here instead of on a user's machine.

info "Smoke-testing the app..."
"$APP/Contents/MacOS/$BUNDLE_NAME" --version || error "App failed to start — a build dependency was likely dropped (see step 1)."
find "$APP" -name libhidapi.dylib | grep -q . \
    || error "libhidapi.dylib is missing from the app — it would fail on Macs without Homebrew hidapi."
# pystray lives inside the bundled PYZ archive, so check the build's module graph instead of the files.
grep -q "pystray._darwin" "build/$BUNDLE_NAME/xref-$BUNDLE_NAME.html" \
    || error "pystray's macOS backend is missing from the app — no menu bar icon."
codesign --verify --deep "$APP" || error "The app's signature does not verify."

# ── Step 4: Assemble archive ─────────────────────────────────────────
# .tar.gz preserves the executable bits and the bundle's symlinks; zip does not reliably.

info "Assembling $ARCHIVE.tar.gz..."
stage="dist/$ARCHIVE"
rm -rf "$stage"
mkdir -p "$stage"
cp -R "$APP" "$stage/"
cp README.md LICENSE.txt docs/Installation.md config.example.yaml "$stage/"
tar -czf "dist/$ARCHIVE.tar.gz" -C dist "$ARCHIVE"
rm -rf "$stage"

# ── Done ─────────────────────────────────────────────────────────────

ok "Release archive ready: dist/$ARCHIVE.tar.gz"
