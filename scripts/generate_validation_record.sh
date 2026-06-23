#!/usr/bin/env bash
set -euo pipefail

# Generate a pre-filled validation record from soak test logs and system info.
#
# Usage:
#   ./scripts/generate_validation_record.sh [soak_log_dir]
#   Default: most recent ~/navbot_soak_* directory
#
# Output: printed to stdout. Redirect to file:
#   ./scripts/generate_validation_record.sh > validation_record_$(date +%Y%m%d).md

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${1:-}" ]]; then
  LOG_DIR="$1"
else
  LOG_DIR=$(ls -dt "$HOME"/navbot_soak_* 2>/dev/null | head -1)
fi

VERSION=$(grep '#define FIRMWARE_VERSION' \
  "${ROOT_DIR}/firmware/makerpi_rp2040_base/include/navbot_protocol.h" \
  | sed 's/.*"\(.*\)".*/\1/' || echo "unknown")
GIT_HASH=$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
GIT_TAG=$(git -C "$ROOT_DIR" describe --tags --exact-match 2>/dev/null || echo "none")

# Extract soak metrics
SOAK_DURATION="N/A"
AVG_LATENCY="N/A"
MAX_LATENCY="N/A"
RECONNECT_DELTA="N/A"
MEM_START="N/A"
MEM_END="N/A"
MEM_DELTA="N/A"
MEM_MIN="N/A"
CHECKSUM_DELTA="N/A"
DISCONNECTIONS="N/A"
KERNEL_WARNINGS="N/A"

if [[ -n "$LOG_DIR" && -d "$LOG_DIR" ]]; then
  if [[ -f "$LOG_DIR/soak_meta.txt" ]]; then
    SOAK_DURATION=$(grep 'Duration target' "$LOG_DIR/soak_meta.txt" | awk '{print $NF}' || echo "N/A")
  fi

  if [[ -f "$LOG_DIR/bridge_health.jsonl" ]]; then
    eval "$(python3 -c "
import json
lines = []
for raw in open('$LOG_DIR/bridge_health.jsonl'):
    raw = raw.strip()
    if not raw: continue
    try: lines.append(json.loads(raw))
    except: continue
if not lines:
    exit(0)
# Latency
lats = [l.get('last_latency_ms') for l in lines if l.get('last_latency_ms') is not None]
if lats:
    print(f'AVG_LATENCY={sum(lats)/len(lats):.2f}')
    print(f'MAX_LATENCY={max(lats):.2f}')
# Reconnects
rc = [l.get('reconnect_count',0) for l in lines]
if rc:
    print(f'RECONNECT_DELTA={rc[-1]-rc[0]}')
# Checksums
cf = [l.get('checksum_failures',0) for l in lines]
if cf:
    print(f'CHECKSUM_DELTA={cf[-1]-cf[0]}')
# Disconnections
dc = sum(1 for l in lines if not l.get('serial_connected', True))
print(f'DISCONNECTIONS={dc}')
" 2>/dev/null || true)"

    eval "$(python3 -c "
import sys
vals = []
for line in open('$LOG_DIR/system.log'):
    if 'Mem:' in line:
        parts = line.split()
        if len(parts) >= 4:
            try: vals.append(int(parts[3]))
            except: pass
if vals:
    print(f'MEM_START={vals[0]}')
    print(f'MEM_END={vals[-1]}')
    print(f'MEM_MIN={min(vals)}')
    print(f'MEM_DELTA={vals[-1]-vals[0]}')
" 2>/dev/null || true)"
  fi

  if [[ -f "$LOG_DIR/kernel_warnings.log" ]]; then
    KERNEL_WARNINGS=$(wc -l < "$LOG_DIR/kernel_warnings.log" | tr -d ' ')
  else
    KERNEL_WARNINGS="0"
  fi
fi

cat << RECORD
# Validation Record

## System Info

| Field | Value |
|-------|-------|
| Firmware Version | ${VERSION} |
| Git Commit | ${GIT_HASH} |
| Git Tag | ${GIT_TAG} |
| Date | $(date -Iseconds) |
| Operator | __________________ |
| Unit Tests | 84 passed (verify before signing) |

## Soak Test Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Duration | ${SOAK_DURATION} | >= 8h | _____ |
| Avg Latency | ${AVG_LATENCY} ms | < 10ms normal | _____ |
| Max Latency | ${MAX_LATENCY} ms | < 50ms | _____ |
| Reconnect Count (delta) | ${RECONNECT_DELTA} | 0 | _____ |
| Checksum Failures (delta) | ${CHECKSUM_DELTA} | 0 | _____ |
| Disconnection Samples | ${DISCONNECTIONS} | 0 | _____ |
| Memory Start | ${MEM_START} MB | — | — |
| Memory End | ${MEM_END} MB | — | — |
| Memory Delta | ${MEM_DELTA} MB | < 50 MB | _____ |
| Memory Min | ${MEM_MIN} MB | > 100 MB | _____ |
| Kernel Warnings | ${KERNEL_WARNINGS} | 0 | _____ |

## Bench Test Results (fill manually)

### Safety Tests
- [ ] S1: Watchdog USB-unplug — motors stop within 250ms
- [ ] S2: Watchdog reboot — PING responds with v${VERSION}
- [ ] S3: ESTOP hardware — immediate motor stop
- [ ] S4: ESTOP race — 50/50 rejections, zero false clears
- [ ] S5: ESTOP recovery — clean reset after release
- [ ] S6: USB disconnect — bridge reconnects with handshake
- [ ] S7: Command timeout — stops at 500ms
- [ ] S8: Stall detection — fault within expected window

### Communication Tests
- [ ] C1: Valid checksum accepted
- [ ] C2: Wrong checksum rejected
- [ ] C3: No checksum accepted (backward compat)
- [ ] C4: Truncated checksum rejected
- [ ] C6: Reconnect handshake verified
- [ ] C7: Firmware version ${VERSION} confirmed
- [ ] C8: DIAG idle — no truncation
- [ ] C9: DIAG under load — non-zero values, no truncation
- [ ] C10: Line overflow rejected

### Sensor Tests
- [ ] I1: IMU rate ~20 Hz — measured: ___ Hz
- [ ] I2: IMU I2C failure → available: false
- [ ] I3: IMU recovery → available: true
- [ ] I4: INA238 available: true
- [ ] I5: INA238 absent → graceful degradation
- [ ] I6: LiDAR rate 8-12 Hz — measured: ___ Hz
- [ ] I7: LiDAR unplug → Stale
- [ ] I8: imu_link in TF tree

### Integration Tests
- [ ] I9: 1m accuracy — measured x: ___ m (threshold: 0.95-1.05)
- [ ] I10: 360° heading — error: ___ deg (threshold: < 10°)

### Security Tests
- [ ] W1: Loopback POST → 200
- [ ] W3: Correct token → 200
- [ ] W4: Wrong token → 401
- [ ] W5: GET always open → 200

## Observations

_Record any anomalies, warnings, or notes here:_




## Final Decision

- [ ] **GO** — all criteria met, no threshold violations
- [ ] **CONDITIONAL GO** — limitations: __________________
- [ ] **NO-GO** — blocked by: __________________

## Signature

| | |
|---|---|
| Name | __________________ |
| Date | $(date +%Y-%m-%d) |
| Role | __________________ |
RECORD
