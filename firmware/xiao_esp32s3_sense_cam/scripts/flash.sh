#!/usr/bin/env bash
# scripts/flash.sh — canonical build / flash / monitor wrapper.
# Usage:
#   ./scripts/flash.sh                       # default port
#   ./scripts/flash.sh /dev/cu.usbmodemXXXX  # override
#   ./scripts/flash.sh --build-only          # skip flash + monitor
set -euo pipefail

PORT_DEFAULT="/dev/cu.usbmodem1401"
IDF_PATH_DEFAULT="$HOME/esp/esp-idf"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FW_DIR="$REPO_ROOT/firmware"

build_only=0
port="$PORT_DEFAULT"
while (( $# > 0 )); do
    case "$1" in
        --build-only) build_only=1 ;;
        -h|--help)
            sed -n '2,8p' "$0"; exit 0 ;;
        /dev/*)       port="$1" ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done

# Source IDF if not already.
if [[ -z "${IDF_PATH:-}" ]]; then
    if [[ ! -f "$IDF_PATH_DEFAULT/export.sh" ]]; then
        echo "ESP-IDF not found at $IDF_PATH_DEFAULT — set IDF_PATH or install IDF." >&2
        exit 1
    fi
    # shellcheck disable=SC1091
    . "$IDF_PATH_DEFAULT/export.sh" >/dev/null
fi

idf.py -C "$FW_DIR" set-target esp32s3 >/dev/null
idf.py -C "$FW_DIR" build

if (( build_only )); then
    echo "build-only: stopping before flash."
    exit 0
fi

if [[ ! -e "$port" ]]; then
    echo "port $port not found. Plugged in? In ROM bootloader? Available:" >&2
    ls /dev/cu.usbmodem* 2>/dev/null || echo "  (none)" >&2
    exit 1
fi

idf.py -C "$FW_DIR" -p "$port" flash monitor
