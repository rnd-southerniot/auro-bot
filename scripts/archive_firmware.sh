#!/usr/bin/env bash
set -euo pipefail

# Archive a built firmware.uf2 with full provenance metadata.
#
# Usage:
#   ./scripts/archive_firmware.sh [path/to/firmware.uf2]
#   Default: firmware/makerpi_rp2040_base/build/firmware.uf2
#
# Creates:
#   firmware_archive/v<VERSION>_<TIMESTAMP>/
#     firmware.uf2
#     metadata.txt
#     SHA256SUMS

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UF2_PATH="${1:-${ROOT_DIR}/firmware/makerpi_rp2040_base/build/firmware.uf2}"

if [[ ! -f "$UF2_PATH" ]]; then
  echo "ERROR: firmware binary not found at: $UF2_PATH" >&2
  echo "Build first: cd firmware/makerpi_rp2040_base/build && cmake .. && make" >&2
  exit 1
fi

# Extract version from protocol header
VERSION=$(grep '#define FIRMWARE_VERSION' "${ROOT_DIR}/firmware/makerpi_rp2040_base/include/navbot_protocol.h" \
  | sed 's/.*"\(.*\)".*/\1/')
if [[ -z "$VERSION" ]]; then
  VERSION="unknown"
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_DIR="${ROOT_DIR}/firmware_archive/v${VERSION}_${TIMESTAMP}"
mkdir -p "$ARCHIVE_DIR"

cp "$UF2_PATH" "$ARCHIVE_DIR/firmware.uf2"

# Compute checksum
CHECKSUM=$(shasum -a 256 "$ARCHIVE_DIR/firmware.uf2")
echo "$CHECKSUM" > "$ARCHIVE_DIR/SHA256SUMS"

# Build metadata
GIT_HASH=$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
GIT_TAG=$(git -C "$ROOT_DIR" describe --tags --exact-match 2>/dev/null || echo "none")
GIT_DIRTY=$(git -C "$ROOT_DIR" diff --quiet 2>/dev/null && echo "clean" || echo "dirty")
UF2_SIZE=$(wc -c < "$ARCHIVE_DIR/firmware.uf2" | tr -d ' ')

cat > "$ARCHIVE_DIR/metadata.txt" << EOF
Firmware Archive
================
Version:     ${VERSION}
Archived:    $(date -Iseconds)
Git commit:  ${GIT_HASH}
Git tag:     ${GIT_TAG}
Git state:   ${GIT_DIRTY}
UF2 size:    ${UF2_SIZE} bytes
SHA256:      $(echo "$CHECKSUM" | awk '{print $1}')
Source:      ${UF2_PATH}
Host:        $(hostname)
EOF

echo ""
echo "Firmware archived successfully."
echo "  Path:     ${ARCHIVE_DIR}"
echo "  Version:  ${VERSION}"
echo "  Commit:   ${GIT_HASH:0:8}"
echo "  Tag:      ${GIT_TAG}"
echo "  SHA256:   $(echo "$CHECKSUM" | awk '{print $1}')"
echo ""
cat "$ARCHIVE_DIR/metadata.txt"
