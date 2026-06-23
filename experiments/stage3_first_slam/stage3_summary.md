# Stage 3 — First Teleop + SLAM Mapping Summary

Date: 2026-04-13
Branch: navbot-experimental
Power: Battery

## Session Profile

- Duration: ~10 minutes (including LiDAR recovery)
- Environment: ~1m x 0.7m area
- Motion: forward, backward, left turn, right turn, one full perimeter loop
- Speeds: low (web console default)

## System Behavior During Motion

- All motor commands responded correctly
- Robot moved in expected directions
- No STALL or ESTOP faults
- No unexpected behavior
- Controller remained IDLE OK after stop

## Key Metrics

| Metric | Value |
|--------|-------|
| Bus voltage (during motion) | 5.047V |
| Temperature | 47C |
| Free memory | 5977 MB |
| Scan | Alive, 720 beams throughout |
| Odom final | x=0.471, y=0.042, yaw=1.586 rad |
| Reconnects | 0 |
| Faults | 0 |

## Map Result

- Map saved: first_map.pgm + first_map.yaml
- Map size: 68 x 116 pixels at 0.05 m/pix (3.4m x 5.8m)
- Map generated from slam_toolbox async mode
- Map reflects the small operating area perimeter

## LiDAR Issue Encountered

- LiDAR node failed to restart after Stage 2 clean shutdown
- Root cause: CP2102 module has no DTR pin; motor cannot be restarted via serial
- Recovery: power-cycled LiDAR; motor restarted on power-up
- Operational rule: do not stop LiDAR node during session; power-cycle to restart

## Classification

FIRST MAP SUCCESSFUL AND SYSTEM STABLE

## Notes

- Battery power held stable at 5.04-5.05V throughout all motion
- No USB re-enumeration during motor load
- slam_toolbox built map without errors
- Odometry and scan data remained coherent
