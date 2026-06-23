#!/usr/bin/env bash
set -euo pipefail

# Post-soak analysis — parses soak test logs and produces a summary.
#
# Usage:
#   ./scripts/soak_analyze.sh [log_directory]
#   Default: most recent ~/navbot_soak_* directory

if [[ -n "${1:-}" ]]; then
  LOG_DIR="$1"
else
  LOG_DIR=$(ls -dt "$HOME"/navbot_soak_* 2>/dev/null | head -1)
fi

if [[ -z "$LOG_DIR" || ! -d "$LOG_DIR" ]]; then
  echo "ERROR: no soak log directory found" >&2
  echo "Usage: $0 [/path/to/navbot_soak_YYYYMMDD_HHMMSS]" >&2
  exit 1
fi

echo "=========================================="
echo "  NAVBOT SOAK TEST ANALYSIS"
echo "  Log directory: $LOG_DIR"
echo "=========================================="
echo ""

# --- Duration ---
echo "=== Duration ==="
if [[ -f "$LOG_DIR/soak_meta.txt" ]]; then
  cat "$LOG_DIR/soak_meta.txt"
else
  echo "  (no soak_meta.txt found)"
fi
echo ""

# --- Disconnections ---
echo "=== Serial Disconnections ==="
if [[ -f "$LOG_DIR/bridge_health.jsonl" ]]; then
  DISCONNECTS=$(grep -c '"serial_connected": false' "$LOG_DIR/bridge_health.jsonl" 2>/dev/null || echo "0")
  TOTAL_SAMPLES=$(wc -l < "$LOG_DIR/bridge_health.jsonl" | tr -d ' ')
  echo "  Disconnection samples: ${DISCONNECTS} / ${TOTAL_SAMPLES} total"
  if [[ "$DISCONNECTS" -gt 0 ]]; then
    echo "  *** FAIL: disconnections detected ***"
  else
    echo "  PASS: zero disconnections"
  fi
else
  echo "  (no bridge_health.jsonl found)"
fi
echo ""

# --- Checksum Failures ---
echo "=== Checksum Failures ==="
if [[ -f "$LOG_DIR/bridge_health.jsonl" ]]; then
  python3 -c "
import json, sys
lines = []
for raw in open('$LOG_DIR/bridge_health.jsonl'):
    raw = raw.strip()
    if not raw:
        continue
    try:
        lines.append(json.loads(raw))
    except json.JSONDecodeError:
        continue
if not lines:
    print('  (no valid health data)')
    sys.exit(0)
start = lines[0].get('checksum_failures', 0)
end = lines[-1].get('checksum_failures', 0)
delta = end - start
print(f'  Start: {start}  End: {end}  Delta: {delta}')
if delta > 10:
    print('  *** FAIL: checksum failures exceeded threshold (>10) ***')
elif delta > 0:
    print('  WARNING: some checksum failures detected')
else:
    print('  PASS: zero checksum failures')
"
else
  echo "  (no data)"
fi
echo ""

# --- Serial Latency ---
echo "=== Serial Latency ==="
if [[ -f "$LOG_DIR/bridge_health.jsonl" ]]; then
  python3 -c "
import json, sys
latencies = []
for raw in open('$LOG_DIR/bridge_health.jsonl'):
    raw = raw.strip()
    if not raw:
        continue
    try:
        d = json.loads(raw)
        v = d.get('last_latency_ms')
        if v is not None:
            latencies.append(float(v))
    except (json.JSONDecodeError, TypeError, ValueError):
        continue
if not latencies:
    print('  (no latency data)')
    sys.exit(0)
avg = sum(latencies) / len(latencies)
mx = max(latencies)
mn = min(latencies)
over_50 = sum(1 for l in latencies if l > 50.0)
print(f'  Samples: {len(latencies)}')
print(f'  Min: {mn:.2f} ms')
print(f'  Avg: {avg:.2f} ms')
print(f'  Max: {mx:.2f} ms')
print(f'  Over 50ms: {over_50}')
if over_50 >= 5:
    print('  *** FAIL: 5+ consecutive samples over 50ms threshold ***')
elif mx > 50.0:
    print('  WARNING: max latency exceeded 50ms')
else:
    print('  PASS: all latencies within threshold')
"
else
  echo "  (no data)"
fi
echo ""

# --- Reconnect Count ---
echo "=== Reconnect Count ==="
if [[ -f "$LOG_DIR/bridge_health.jsonl" ]]; then
  python3 -c "
import json, sys
counts = []
for raw in open('$LOG_DIR/bridge_health.jsonl'):
    raw = raw.strip()
    if not raw:
        continue
    try:
        d = json.loads(raw)
        v = d.get('reconnect_count')
        if v is not None:
            counts.append(int(v))
    except (json.JSONDecodeError, TypeError, ValueError):
        continue
if not counts:
    print('  (no data)')
    sys.exit(0)
start = counts[0]
end = counts[-1]
delta = end - start
print(f'  Start: {start}  End: {end}  Delta: {delta}')
if delta > 3:
    print('  *** FAIL: reconnects exceeded threshold (>3/hour) ***')
elif delta > 0:
    print('  WARNING: reconnections detected during soak')
else:
    print('  PASS: zero reconnections during soak')
"
else
  echo "  (no data)"
fi
echo ""

# --- Memory ---
echo "=== Memory Trend ==="
if [[ -f "$LOG_DIR/system.log" ]]; then
  grep 'Mem:' "$LOG_DIR/system.log" | awk '{print $4}' | python3 -c "
import sys
vals = []
for line in sys.stdin:
    line = line.strip()
    if line:
        try:
            vals.append(int(line))
        except ValueError:
            pass
if not vals:
    print('  (no memory data)')
    sys.exit(0)
print(f'  Samples: {len(vals)}')
print(f'  Start: {vals[0]} MB')
print(f'  End: {vals[-1]} MB')
print(f'  Min: {min(vals)} MB')
print(f'  Max: {max(vals)} MB')
print(f'  Delta: {vals[-1] - vals[0]} MB')
if min(vals) < 100:
    print('  *** FAIL: free memory dropped below 100 MB ***')
elif abs(vals[-1] - vals[0]) > 50:
    print('  *** FAIL: memory drift exceeded 50 MB ***')
else:
    print('  PASS: memory stable')
"
else
  echo "  (no data)"
fi
echo ""

# --- CPU / Temperature ---
echo "=== CPU Load ==="
if [[ -f "$LOG_DIR/system.log" ]]; then
  grep -E '^[0-9]+\.' "$LOG_DIR/system.log" | awk '{print $1}' | python3 -c "
import sys
vals = []
for line in sys.stdin:
    line = line.strip()
    if line:
        try:
            vals.append(float(line))
        except ValueError:
            pass
if not vals:
    print('  (no load data)')
    sys.exit(0)
avg = sum(vals) / len(vals)
mx = max(vals)
print(f'  Samples: {len(vals)}')
print(f'  Avg 1-min load: {avg:.2f}')
print(f'  Max 1-min load: {mx:.2f}')
if mx > 3.5:
    print('  WARNING: peak load exceeded 3.5')
else:
    print('  PASS: load within range')
"
else
  echo "  (no data)"
fi
echo ""

# --- Kernel Warnings ---
echo "=== Kernel Warnings ==="
if [[ -f "$LOG_DIR/kernel_warnings.log" ]]; then
  WARNINGS=$(wc -l < "$LOG_DIR/kernel_warnings.log" | tr -d ' ')
  echo "  Warning lines: ${WARNINGS}"
  if [[ "$WARNINGS" -gt 0 ]]; then
    echo "  *** FAIL: kernel warnings detected ***"
    echo "  Contents:"
    head -20 "$LOG_DIR/kernel_warnings.log" | sed 's/^/    /'
  else
    echo "  PASS: zero kernel warnings"
  fi
else
  echo "  PASS: no kernel warning file (none captured)"
fi
echo ""

# --- Topic Rates ---
echo "=== Topic Rate Summary ==="
if [[ -f "$LOG_DIR/topic_rates.log" ]]; then
  echo "  Top rate readings:"
  grep 'average rate' "$LOG_DIR/topic_rates.log" | sort | uniq -c | sort -rn | head -10 | sed 's/^/    /'
else
  echo "  (no data)"
fi
echo ""

echo "=========================================="
echo "  ANALYSIS COMPLETE"
echo "=========================================="
