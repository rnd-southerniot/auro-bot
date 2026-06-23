# Stage 4 — Map Quality & Repeatability Summary

Date: 2026-04-14
Branch: navbot-experimental
Power: Battery

## Comparison Table

| Metric | Run 1 | Run 2 | Run 3 |
|--------|-------|-------|-------|
| Map size (px) | 203 x 87 | 124 x 84 | 81 x 111 |
| Odom delta dx | 0.016 m | 0.225 m | 0.027 m |
| Odom delta dy | 0.310 m | -0.144 m | -0.278 m |
| Odom delta yaw | -0.957 rad | -1.035 rad | -0.975 rad |
| Motor V avg | 5.119 V | 5.114 V | 5.114 V |
| Motor V min | 5.071 V | 5.075 V | 5.085 V |
| LiDAR V avg | 4.891 V | 4.880 V | 4.763 V |
| LiDAR V min | 4.868 V | 4.858 V | 4.506 V |
| Controller | IDLE OK | IDLE OK | IDLE OK |
| Faults | 0 | 0 | 0 |
| Reconnects | 0 | 0 | 0 |

## Analysis

### Map consistency
- Map sizes differ significantly (203x87 vs 124x84 vs 81x111), indicating
  that the area covered and SLAM integration varied between runs.
- This is expected given manual teleop — the operator cannot reproduce
  exact timing and path geometry without waypoint control.
- All three maps were successfully generated and saved.

### Drift
- Odom endpoint drift varies between runs (0.31m, 0.27m, 0.28m magnitude).
- Yaw drift is relatively consistent (~0.96-1.04 rad per loop).
- The drift magnitude suggests wheel calibration can be improved but is
  within reasonable range for uncalibrated odometry.

### Loop closure
- slam_toolbox did not report loop closure errors.
- Map generation completed for all runs.
- Alignment quality cannot be fully assessed without visual map overlay.

### Power correlation
- Motor voltage was rock-solid across all 3 runs (5.07-5.14V range).
- LiDAR voltage degraded progressively:
  - Run 1: avg 4.891V (min 4.868V)
  - Run 2: avg 4.880V (min 4.858V)
  - Run 3: avg 4.763V (min 4.506V) — significant drop
- The LiDAR battery is depleting across runs.
- Run 3 map size was different, possibly correlating with lower LiDAR
  voltage affecting scan quality in the later portion of the run.

## Classification

MINOR DRIFT (ACCEPTABLE) — with note: POWER-SENSITIVE on LiDAR rail

The system produces maps consistently with acceptable drift for
uncalibrated odometry. However, the LiDAR battery depletion across
runs introduces a time-dependent variable that could affect longer
mapping sessions. Motor power remained completely stable.

## Recommendation

Proceed to Stage 5 (navigation) after:
1. Charging the LiDAR battery (dropped to 4.5V during Run 3)
2. Considering wheel calibration refinement to reduce per-run drift
