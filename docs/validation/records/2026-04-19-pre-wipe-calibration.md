# Pre-Wipe Kinematic Calibration Record

**Date:** 2026-04-19
**Session:** Final verification before Pi wipe + clean reinstall
**Firmware:** 1.2.0 (flashed Phase A session)
**Commit:** b15196f
**Operator:** Arif
**Verdict:** EXCELLENT — no calibration changes needed

## Physical Measurements

| Move | Commanded | Odom | Physical | Δ odom-phys |
|------|----------:|-----:|---------:|------------:|
| M1 forward | 300 mm | 258.0 mm | 258 mm | 0.0 mm |
| M2 spin 90° left | 90.00° | +80.26° | +80° | +0.26° |
| M3 forward | 300 mm | 261.6 mm | 261 mm | +0.6 mm |

## Findings

- `wheel_radius = 0.0325 m` — correct (odom distance = physical distance)
- `wheel_separation = 0.180 m` — correct (odom rotation = physical rotation)
- CPR (left=3943, right=3946, default=3945) — correct
- Firmware + geometry: self-consistent

## Time-Based Shortfall Note

Commanded 300 mm achieved ~260 mm under 3-second time-based `drive_on_heading`. This is **not a calibration error** — caused by firmware control ramp:
- 333 ms duty slew rate
- 282 ms velocity filter settling

Under Nav2 DWB or `behavior_server` with odom feedback, the controller closes the loop on actual distance and will achieve commanded distance correctly.

## Validation Baseline

Post-wipe, the same test sequence on the new Pi should produce:
- M1 forward: physical 258 ± 5 mm (within ±2% of this record)
- M2 spin: physical 80 ± 2° (within ±2° of this record)
- M3 forward: physical 261 ± 5 mm

Deviation beyond these bands indicates either:
1. Different firmware binary (check UF2 hash)
2. Different battery state of charge
3. Hardware change since this record

## Known Deferred Items

- **C7**: `/base/motor_voltage` reports divider-scaled rail (5.13 V), not raw battery (8.67 V). Divider ratio 1.691. Fix in Phase C either in firmware telemetry or navbot_base publisher.
- **LiDAR forward gate discrepancy**: investigated briefly, not resolved. LiDAR itself confirmed healthy (720-beam 360° at 10 Hz). Investigate post-wipe with clean diagnostic scripts.

