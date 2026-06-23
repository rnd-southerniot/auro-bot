# Counter-Drive Session 2026-04-20 — Handoff

Session deferred at Phase 0.5c. Counter-drive work did not reach the
implementation phase. Hardware in mid-state — next session must resolve
before resuming.

## Session scope (intended)

Design, implement, bench-validate, and floor-validate firmware active
counter-drive to reduce post-stop coast-on from 17 mm baseline at 0.05 m/s.
Full plan preserved in session prompt; summarised in
[../project-status.md](../project-status.md).

## What completed successfully

- **Phase 0 inventory** — firmware structure mapped
  ([src/wheel.c](../../firmware/makerpi_rp2040_base/src/wheel.c),
  [src/main.c](../../firmware/makerpi_rp2040_base/src/main.c),
  [src/safety.c](../../firmware/makerpi_rp2040_base/src/safety.c)),
  control loop confirmed 100 Hz with per-motor `wheel_t` FSM
  (`WMODE_IDLE` / `WMODE_SPEED`), no existing hardware current sense,
  RP2040 hardware watchdog already consumed by main loop at 200 ms.
- **Phase 0.5a** — `NAVBOT_CMD_TEST_PWM` bench debug command added
  (commit `f2b6877`, tag `pre-counterdrive-code-v1`). Compiles clean,
  +808 bytes text, zero warnings. Not yet flashed to RP2040.
- **Physical INA238 relocation** — moved from Pi compute rail (System 1)
  to motor rail (System 3) as high-side shunt. STEMMA QT / I²C still on
  Pi, driver unchanged. Wire topology: battery+ → INA238 VIN+ → shunt →
  INA238 VIN− → Maker Pi VIN. Single path, no JST bypass, all grounds
  common.
- **INA238 chip still enumerates** on Pi I²C bus 1 at `0x40`. Driver
  publishes at 2 Hz. `bus_voltage_v` responds correctly to motor pack
  switch (0.97 V floating OFF, 5.07 V with pack ON) → VIN+ wire makes
  contact.

## What's unresolved / broken

- **INA238 `current_a` reads 0.0 A during motor pulses** despite
  multimeter-in-series confirming > 50 mA flowing through battery wire.
- **INA238 `shunt_voltage_v` reads 0 V or ±1 LSB noise** during same
  pulses → shunt sees no voltage drop.
- By Ohm's law: real current + zero shunt voltage ⇒ **shunt resistance
  effectively zero** → **primary hypothesis: Adafruit INA238 breakout
  shunt is physically shorted** (solder bridge, conductive debris under
  screw terminal, or failed resistor). Not yet confirmed by DMM-across-
  shunt test.
- **GP27 ADC voltage divider for `/base/motor_voltage` was disconnected**
  as part of relocation. `/base/motor_voltage` now reports ~0 V and is
  unreliable. Ground-truth motor rail voltage comes from
  `/power/ina238/bus_voltage_v` only.
- **Counter-drive still blocked** on motor-rail current visibility.

## Hardware state as left at session close

| Item | State |
|---|---|
| INA238 VIN+ | wired to motor battery pack positive terminal |
| INA238 VIN− | wired to Maker Pi RP2040 VIN pin |
| INA238 VBUS jumper | CLOSED (high-side sense) |
| INA238 VS | Pi 3.3 V GPIO (unchanged) |
| INA238 STEMMA QT | Pi I²C bus 1, addr `0x40` (unchanged) |
| GP27 ADC divider | disconnected |
| Motor battery pack | charged, same as prior sessions |
| Pi power | USB-C wall adapter |
| RP2040 firmware on chip | 1.2.0 (last flashed) |
| Source tree firmware | 1.3.0 with TEST_PWM compiled in (commit `f2b6877`) |

## Diagnostic test pending

**DMM-across-shunt during pulse** — the one test that cleanly disambiguates
hardware vs. software cause of the zero-current reading.

Procedure:
1. Motor pack ON, wheels lifted and secured
2. DMM set to **DC mV** range, probes directly on INA238 breakout
   `VIN+` and `VIN−` screw terminals
3. `ros2 topic pub -1 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.15}}"`
4. Watch DMM for 3 seconds
5. `ros2 topic pub -1 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}}"`

**Interpretation:**

- **2-10 mV on DMM during pulse** → shunt works at hardware level.
  Driver calibration issue (likely SHUNT_CAL register lost/wrong after
  relocation). Fix in driver — no hardware swap needed.
- **0-0.5 mV on DMM during pulse** → shunt physically shorted. Visual
  inspect breakout for solder bridge / debris / frayed wire under screw
  clamp. If nothing visible, replace Adafruit INA238 breakout.

## Observations worth keeping for next session

- Cytron Maker Pi RP2040 USB-C port can source motor current
  independently of the VIN/battery path. When the battery path is
  degraded or zero-current, motors can still twitch briefly from USB
  power (saw ~17 mm motion at zero battery current during this session).
  Useful for future "is battery actually sourcing?" diagnoses.
- INA238 with VBUS jumper CLOSED and VIN+ floating reads ~1 V on VBUS,
  not clean 0 V. Good "is the VIN+ wire connected?" indicator — real
  battery → 5 V, floating → 1 V, hard short to GND → 0 V.

## Next session entry checklist

Before re-starting counter-drive work:

1. Run the DMM-across-shunt test above
2. Based on reading, either:
   - Fix driver (if shunt works) — investigate SHUNT_CAL register write
     in [ina238_reader.py](../../ros2_ws/src/navbot_power/navbot_power/ina238_reader.py)
     and log raw register dump during init, OR
   - Fix hardware (if shunt shorted) — visually inspect, clean, or
     replace breakout
3. Verify INA238 reports plausible current (> 50 mA) during a 0.15 m/s
   pulse
4. Decide whether to restore GP27 ADC divider for `/base/motor_voltage`
   or rely on `/power/ina238/bus_voltage_v` going forward
5. Only then proceed to Phase 0.5d (flash TEST_PWM, locked-rotor
   armature R measurement)

## Counter-drive plan summary (for reference next session)

Design locked by user this session:

- Firmware-only trigger (no Pi-side decision loop)
- Per-motor FSM with shared abort on any fault
- Trigger: cmd_vel zero-transition + measured |v| > MIN_ACTIVATION_SPEED
  + N_DEBOUNCE_TICKS consecutive cmd_vel=0 ticks
- Safety: HW watchdog (alarm timer, 200 ms max pulse) + encoder-gated
  termination + PWM cap 15% + shared abort + encoder anomaly fault
- **No I_FAULT_THRESHOLD firmware check** — Pi telemetry too slow for
  real-time safety. Current safety bounded by PWM cap × armature R
  calculation, verified by empirical R measurement
- Pi-side optional forensic subscriber for peak-current logging during
  CD pulses (Phase 4 bench prep, not on safety path)

## Brake-forensic retro-note (not addressed this session)

User observation to record in
[brake-attempt-forensic.md](brake-attempt-forensic.md) next time:
Cytron Maker Pi RP2040 datasheet documents `IN1 = IN2 = HIGH` as **COAST
(Hi-Z)**, not brake. The brake attempt at commit `dc07888` applied
`IN1 = IN2 = HIGH` intending regenerative brake. If the datasheet
observation is correct, the "ineffective brake" finding may actually
have been "accidentally implementing coast." Worth a retrospective note
in the forensic README. Low priority, separate commit.
