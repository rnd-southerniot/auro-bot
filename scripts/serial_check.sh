#!/usr/bin/env bash
set -euo pipefail

echo "Scanning for likely RP2040 serial devices..."
shopt -s nullglob
devices=(/dev/ttyACM* /dev/ttyUSB*)
shopt -u nullglob

if [ "${#devices[@]}" -eq 0 ]; then
  echo "No /dev/ttyACM* or /dev/ttyUSB* devices found."
  exit 0
fi

printf 'Detected devices:\n'
for dev in "${devices[@]}"; do
  printf '  %s\n' "${dev}"
done

echo
echo "Suggested manual checks:"
echo "  python3 -m serial.tools.miniterm /dev/ttyACM0 115200"
echo "  screen /dev/ttyACM0 115200"
echo
echo "Expected bench command: PING"
echo "Expected response:     ACK PING"
