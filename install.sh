#!/bin/sh
# Installs the standalone evalkit executable from a GitHub Release.
#
#   curl -fsSL https://raw.githubusercontent.com/superintelligenceco/evalkit/main/install.sh | sh
#
# Environment variables:
#   EVALKIT_VERSION      release tag to install, such as v0.2.0 (default: the latest release)
#   EVALKIT_INSTALL_DIR  where to put the executable (default: $HOME/.local/bin)
set -eu

REPO="superintelligenceco/evalkit"
VERSION="${EVALKIT_VERSION:-latest}"
INSTALL_DIR="${EVALKIT_INSTALL_DIR:-$HOME/.local/bin}"

say() { printf 'evalkit-install: %s\n' "$*"; }
fail() { printf 'evalkit-install: error: %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Linux) os=linux ;;
  Darwin) os=macos ;;
  MINGW* | MSYS* | CYGWIN*)
    fail "on Windows, download evalkit-windows-x64.exe from https://github.com/$REPO/releases" ;;
  *) fail "unsupported OS: $(uname -s)" ;;
esac

case "$(uname -m)" in
  x86_64 | amd64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) fail "unsupported CPU architecture: $(uname -m)" ;;
esac

asset="evalkit-$os-$arch"
if [ "$VERSION" = "latest" ]; then
  base="https://github.com/$REPO/releases/latest/download"
else
  case "$VERSION" in v*) ;; *) VERSION="v$VERSION" ;; esac
  base="https://github.com/$REPO/releases/download/$VERSION"
fi

if command -v curl > /dev/null 2>&1; then
  fetch() { curl -fsSL --retry 3 -o "$2" "$1"; }
elif command -v wget > /dev/null 2>&1; then
  fetch() { wget -q -O "$2" "$1"; }
else
  fail "curl or wget is required"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT INT TERM

say "downloading $asset ($VERSION)"
fetch "$base/$asset" "$tmp/$asset" || fail "could not download $base/$asset"
fetch "$base/SHA256SUMS" "$tmp/SHA256SUMS" || fail "could not download $base/SHA256SUMS"

expected="$(awk -v f="$asset" '$2 == f || $2 == "*" f { print $1 }' "$tmp/SHA256SUMS")"
[ -n "$expected" ] || fail "$asset is not listed in SHA256SUMS"
if command -v sha256sum > /dev/null 2>&1; then
  actual="$(sha256sum "$tmp/$asset" | awk '{ print $1 }')"
elif command -v shasum > /dev/null 2>&1; then
  actual="$(shasum -a 256 "$tmp/$asset" | awk '{ print $1 }')"
else
  fail "sha256sum or shasum is required to verify the download"
fi
[ "$expected" = "$actual" ] || fail "checksum mismatch for $asset"
say "checksum ok"

mkdir -p "$INSTALL_DIR"
chmod +x "$tmp/$asset"
if [ "$os" = "macos" ]; then
  xattr -d com.apple.quarantine "$tmp/$asset" 2> /dev/null || true
fi
mv "$tmp/$asset" "$INSTALL_DIR/evalkit"
say "installed $("$INSTALL_DIR/evalkit" --version) to $INSTALL_DIR/evalkit"

case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *) say "add $INSTALL_DIR to your PATH, for example: export PATH=\"$INSTALL_DIR:\$PATH\"" ;;
esac
