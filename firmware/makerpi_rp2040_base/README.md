# makerpi_rp2040_base

Milestone 1 RP2040 base firmware for `makerpi-rp2040-ros2-navbot`.

This firmware now contains a real, minimal drivetrain port from the inspected baseline:

- PWM motor output on the Maker Pi RP2040
- quadrature encoder sampling via PIO
- per-wheel speed PID in counts/sec
- line-based navbot serial protocol
- differential-drive conversion for `CMD_VEL`
- fixed-rate `STATE` and `ODOM` telemetry
- command timeout auto-stop
- estop and stall safety enforcement
- optional continuous-run safety guard

## Explicit Wheel Mapping

The baseline repo had conflicting left/right naming between docs and pin aliases. This firmware resolves that explicitly:

- Left wheel:
  - M2 / GP10-GP11
  - encoder GP2-GP3
  - CPR default `3943`
- Right wheel:
  - M1 / GP8-GP9
  - encoder GP4-GP5
  - CPR default `3946`
  - `swap_dir` enabled so positive command means robot-forward motion

## Implemented for Milestone 1

- `PING`, `STOP`, `RESET`, `ESTOP`
- `CMD_VEL <linear_mps> <angular_rps>`
- `WHEEL_VEL <left_mps> <right_mps>`
- `ACK`, `ERR`, `STATE`, `ODOM`
- 100 Hz control loop
- 10 Hz telemetry

## Firmware Version Banner

`FIRMWARE_VERSION` is defined in `include/navbot_protocol.h` and shipped
in the `ACK PING <version>` reply so an operator can read the running
firmware over serial without flashing.

**Convention (established 2026-04):** bump the version on **every
experiment-and-revert cycle**, not only on net functional changes. This
gives a unit's `ACK PING` reply clear provenance for which post-freeze
iteration is running, even when a cycle ends with no behavioral delta.

- `v1.2.0` is the tagged validation-freeze release
  (`v1.2.0-validation-freeze`, recorded in
  [../../docs/validation/records/2026-04-13-record.md](../../docs/validation/records/2026-04-13-record.md)).
- `v1.3.0` is the current source version. Covers: brake patch
  experiment (attempted, reverted — see
  [../../docs/notes/brake-attempt-forensic.md](../../docs/notes/brake-attempt-forensic.md))
  and the INA238 session (no firmware source changes, but procedural
  bump per convention).

## Runtime Safety Behavior

- `ESTOP` remains latched until `RESET` succeeds with the estop input released.
- command timeout remains active and still stops motion after `COMMAND_TIMEOUT_MS`.
- stall protection remains active and still latches a `STALL` fault.
- stall detection now includes a short startup/reversal grace window before it begins accumulating a `STALL` fault.
- a near-zero wheel speed setpoint now drops the wheel into `IDLE` instead of holding closed-loop speed control at standstill.
- `RUN_TIMEOUT` is now disabled by default for ROS/mobile use by setting `MAX_RUN_TIME_MS` to `0`.

Why:

- the previous `60000 ms` limit was appropriate as a bench-only guard
- it was too strict for normal low-speed ROS drive and soak testing
- communication loss is already handled by command timeout, and mechanical problems are already handled by stall detection
- low-speed ground launches and reversals can briefly build motor duty before encoder motion fully settles, so stall accumulation is delayed briefly after a meaningful setpoint change
- a true stop command should not keep the stall detector armed against a wheel that is intentionally stationary

If you want the old style of bench-only continuous-run fault, set `MAX_RUN_TIME_MS` to a positive value and rebuild.

## Intentionally Left Out

- IMU integration
- heading hold
- position motion primitives
- USB disconnect fault handling
- persistent configuration or calibration storage

## Build

Toolchain preflight:
- if the build fails with `arm-none-eabi-gcc: fatal error: cannot read spec file 'nosys.specs'`, the problem is usually a local incomplete ARM embedded toolchain
- that is not a Pico SDK or navbot CMake layout problem
- do not hardcode repo-local specs paths
- install `arm-none-eabi-newlib` if available, or install a complete Arm GNU embedded toolchain bundle

```bash
export PICO_SDK_PATH=/path/to/pico-sdk
cd firmware/makerpi_rp2040_base
cmake -B build -S .
cmake --build build -j
```

If you do not already have a Pico SDK checkout, you can let CMake fetch one:

```bash
cd firmware/makerpi_rp2040_base
cmake -B build -S . -DPICO_SDK_FETCH_FROM_GIT=ON
cmake --build build -j
```

## Manual Validation

Use wheels lifted or the robot on blocks for the first pass.

```bash
python3 tools/manual_serial_check.py --port /dev/ttyACM0 --send PING --stream-seconds 1.0
python3 tools/manual_serial_check.py --port /dev/ttyACM0 --send "WHEEL_VEL 0.05 0.05" --stream-seconds 2.0
python3 tools/manual_serial_check.py --port /dev/ttyACM0 --send STOP --stream-seconds 1.0
python3 tools/manual_serial_check.py --port /dev/ttyACM0 --send "CMD_VEL 0.10 0.00" --stream-seconds 2.0
python3 tools/manual_serial_check.py --port /dev/ttyACM0 --send "CMD_VEL 0.00 1.00" --stream-seconds 2.0
```

Minimum pass criteria:

- `PING` returns `ACK PING`.
- forward wheel commands rotate both wheels robot-forward.
- forward wheel commands make both encoder counts increase.
- `CMD_VEL 0.10 0.00` drives straight-forward wheel motion.
- `CMD_VEL 0.00 1.00` follows ROS yaw convention: left wheel reverse, right wheel forward.
- `STOP` returns the controller to `IDLE OK`.
- command timeout stops motion after fresh commands stop.
- `ESTOP` latches a stop and `RESET` clears only after the estop input is released.

Use `tools/manual_serial_check.py` for deeper serial inspection. Keep the firmware text protocol human-readable for bench diagnostics.

## Related Docs

- Flashing procedure: [FLASHING.md](FLASHING.md)
- System architecture (Pi ↔ RP2040 split): [../../docs/architecture/system.md](../../docs/architecture/system.md)
- Runbook (pre-flight + incident response): [../../docs/RUNBOOK.md](../../docs/RUNBOOK.md)
- Brake experiment forensic (archived): [../../docs/notes/brake-attempt-forensic.md](../../docs/notes/brake-attempt-forensic.md)
- Motion test results (firmware validation): [../../docs/testing/motion-tests.md](../../docs/testing/motion-tests.md)
- Project status (firmware backlog items): [../../docs/project-status.md](../../docs/project-status.md)
