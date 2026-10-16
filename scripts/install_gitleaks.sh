#!/usr/bin/env bash
# Install the pinned gitleaks release into a directory OUTSIDE the repository.
#
# Usage:   scripts/install_gitleaks.sh <dest-dir>
# Offline: GITLEAKS_TARBALL=/path/to/gitleaks_8.30.1_linux_x64.tar.gz scripts/install_gitleaks.sh <dest-dir>
#
# The archive is obtained by one of two routes - the pinned release download, or a
# pre-downloaded file named by GITLEAKS_TARBALL (for a host where the release
# download is unreachable). Both routes are verified against the SAME pinned sha256
# before anything is extracted, so a pre-downloaded archive gets exactly the same check.
#
# Exit codes: 0 installed, 2 bad arguments / unusable destination / unreadable
# GITLEAKS_TARBALL, 1 checksum mismatch or download failure.
set -euo pipefail

GITLEAKS_VERSION="8.30.1"
GITLEAKS_SHA256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
ASSET="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
URL="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${ASSET}"

if [ "$#" -ne 1 ]; then
  echo "usage: scripts/install_gitleaks.sh <dest-dir>   (optional env GITLEAKS_TARBALL=<path>)" >&2
  exit 2
fi

DEST=$(realpath -m -- "$1")

# Refuse a destination inside any git work tree we run from, so a downloaded
# archive can never be scanned or committed.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
for probe in "$PWD" "$SCRIPT_DIR"; do
  if TOP=$(git -C "$probe" rev-parse --show-toplevel 2>/dev/null); then
    case "$DEST/" in
      "$TOP"/*)
        echo "gitleaks: refusing destination $DEST inside the repository $TOP" >&2
        exit 2
        ;;
    esac
  fi
done

mkdir -p -- "$DEST"
ARCHIVE="$DEST/$ASSET"

if [ -n "${GITLEAKS_TARBALL:-}" ]; then
  if [ ! -f "$GITLEAKS_TARBALL" ] || [ ! -r "$GITLEAKS_TARBALL" ]; then
    echo "gitleaks: GITLEAKS_TARBALL is not a readable file" >&2
    exit 2
  fi
  cp -- "$GITLEAKS_TARBALL" "$ARCHIVE"
  echo "gitleaks: using pre-downloaded archive"
else
  curl -sSfL -o "$ARCHIVE" "$URL"
  echo "gitleaks: downloaded release archive"
fi

if ! echo "${GITLEAKS_SHA256}  ${ARCHIVE}" | sha256sum -c - >/dev/null; then
  echo "gitleaks: sha256 mismatch for ${ASSET}; refusing to extract" >&2
  rm -f -- "$ARCHIVE"
  exit 1
fi
echo "gitleaks: sha256 verified (${GITLEAKS_SHA256})"

tar -xzf "$ARCHIVE" -C "$DEST" gitleaks
"$DEST/gitleaks" version
