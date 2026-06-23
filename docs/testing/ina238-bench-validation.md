# INA238 Bench Validation

**Date:** 2026-04-20
**Session:** Counter-drive firmware preparation, INA238 diagnosis
**Outcome:** INA238 chip and shunt wiring validated as fully functional. Root cause of "zero readings" identified as power-path bypass on boards with multi-input power selectors.

## Context

The counter-drive firmware session (see [docs/notes/counter-drive-session-handoff.md](../notes/counter-drive-session-handoff.md)) deferred at Phase 0 because the relocated INA238 on the motor rail was reading near-zero current despite the motor drawing expected current. This document captures the bench validation that resolved the diagnostic ambiguity.

## Test Rig

A spare Cytron Robo Pico board with Pico 2W, configured as an isolated bench instrument. The INA238 under test was moved from the main robot to this rig, allowing diagnosis independent of Pi-side ROS 2 software stack.

### Hardware

| Component | Role |
|---|---|
| Raspberry Pi Pico 2W | Running MicroPython test harness |
| Cytron Robo Pico | Motor driver (MX1508 equivalent), power input, button interface |
| Adafruit INA238 breakout | Device under test |
| Cytron magnetic encoder micro gearmotor (6V nominal) | Load |
| 6V battery pack | Motor power, fed through INA238 shunt |

### Wiring

```
Battery (+)  →  INA238 VIN+                     [high-side shunt]
INA238 VIN-  →  Robo Pico VIN terminal
Battery (-)  →  Robo Pico GND

INA238 VBUS jumper: CLOSED (reads battery voltage directly)
INA238 VS:          3.3V from Pico (via STEMMA QT cable)
INA238 I²C:         Pico I²C1 (SDA=GP2, SCL=GP3) via Maker Port
INA238 address:     0x40

Motor terminals:    Robo Pico M1A/M1B (GP8/GP9 PWM)
Buttons:            GP20 (START), GP21 (STOP) - onboard
```

### Software

Test harness: [scripts/bench/ina238_motor_test.py](../../scripts/bench/ina238_motor_test.py)

Written in MicroPython, uses raw smbus-style I²C for explicit register control. No external INA23x library dependency — register-level implementation for transparency.

## Test Procedure

1. Power up via USB (Thonny for serial console).
2. Verify INA238 initialization passes all register write/readback checks.
3. Verify I²C scan shows 0x40.
4. Baseline: observe idle current (no motor command).
5. Press GP20 button: triggers 500ms forward pulse at 30% PWM.
6. Observe current profile during pulse (inrush vs steady state).
7. Repeat pulses; capture peak and steady-state current per pulse.

## Results

### Initialization

```
MANUFACTURER_ID (0x3E): 0x5449  ✓ (TI)
DEVICE_ID (0x3F):       0x2381  ✓ (INA238 rev B)
CONFIG wrote 0x0010, read 0x0010  ✓
ADC_CONFIG wrote 0xFB69, read 0xFB69  ✓
SHUNT_CAL wrote 3000 (0x0BB8), read 3000  ✓
CURRENT_LSB = 61.04 µA/bit
```

All register write/readback operations successful. INA238 identity confirmed as rev B.

### Configuration

| Parameter | Value | Rationale |
|---|---|---|
| ADCRANGE | 1 (±40.96 mV) | Better resolution for expected motor currents < 2A |
| Conversion time (VBUS, VSHUNT, DIETEMP) | 1052 µs (5h) | Balance between settling and update rate |
| Averaging | 4 samples (1h) | Noise reduction at ~90 Hz effective update rate |
| Max expected current | 2.0 A | Covers 1.5A peak per-channel rating with margin |
| CURRENT_LSB | 61.04 µA/bit | Derived from 2A / 2^15 |
| SHUNT_CAL | 3000 (0x0BB8) | = 819.2e6 × CURRENT_LSB × 0.015 Ω × 4 |

### Idle Baseline (motors not commanded)

At 6.23V battery input:

| Metric | Value |
|---|---|
| VBUS | 6.23 V |
| Current | 18.6 mA (steady) |
| Shunt voltage | 0.28 mV (consistent) |
| Power | 116 mW |
| Noise floor | ±0.3 mA, ±0.002 mV |

The 18.6 mA idle current accounts for Pico 2W logic, Robo Pico onboard regulators, INA238 itself, and GPIO status LEDs. Reasonable for the platform.

### Motor Pulse Profile (30% PWM, 500ms, lifted wheel, no mechanical load)

Typical pulse (14 pulses captured, all consistent):

| Phase | Time | Current | Shunt voltage |
|---|---|---|---|
| Inrush (motor accelerating) | 0-100 ms | 145-151 mA peak | 2.17-2.27 mV |
| Steady state (motor coasting at no-load RPM) | 200-500 ms | 60-80 mA | 0.9-1.1 mV |
| VBUS sag under load | during pulse | -30 mV (6.23→6.20V) | — |

**Peak-to-steady ratio:** approximately 2.4×. Consistent with textbook DC motor inrush behavior due to rotor inertia overcoming starting torque requirements.

### Repeatability

14 consecutive pulses under identical conditions. Peak current varied from 145 to 151 mA (3.5% spread). Steady state varied from 57 to 80 mA (motor thermal drift / gear stiction effects).

### Internal Consistency Check

Hand-verification of readings:

- Steady-state current: 75 mA
- Shunt voltage at 75 mA × 0.015 Ω = 1.125 mV
- Measured shunt voltage: 0.93-1.13 mV ✓

Measurements agree with Ohm's law calculation. INA238 internal math (CURRENT = VSHUNT / R_SHUNT, scaled by SHUNT_CAL) is consistent.

## Critical Finding: Multi-Input Power Selector Interference

### The Symptom

Initial test runs with motor battery at 5.17V while Pico was USB-connected (USB provides ~5.0-5.1V) showed:

| Metric | Reading | Expected |
|---|---|---|
| VBUS | 5.17 V | 5.17 V ✓ |
| Idle current | 0.1 mA | ~18 mA |
| Pulse peak current | 0.8-1.1 mA | 100-200 mA |
| Motor behavior | Spinning normally | Spinning normally |

The motor was clearly operating, drawing substantial current, yet the INA238 saw near-zero current through its shunt.

### The Root Cause

Cytron Robo Pico (and structurally-similar Maker Pi RP2040) has a **Multiple Power Input Selector** that picks the highest-voltage active input from: USB, VIN terminal, and LiPo JST connector. See [Robo Pico datasheet Rev 1.0, Section 6: Power Tree](https://www.cytron.io/) for circuit details.

When battery voltage (5.17V) and USB voltage (~5.1V) are close, current flows from both sources in parallel. The dominant source — often USB because it's a stiff low-impedance supply — provides most of the motor current. That current bypasses the INA238 shunt entirely because USB power enters the board through a different path.

### The Fix

Ensure motor battery voltage clearly exceeds USB voltage. Verified working at 6.23V battery: all motor current flows through VIN terminal (and thus through the shunt), INA238 reads full expected current profile including inrush and steady-state.

### Why This Matters For the Main Robot

The main robot's Maker Pi RP2040 has identical power input selector behavior. During the failed counter-drive relocation session:

- Maker Pi RP2040 was connected via USB to Pi (for serial bridge)
- 5V motor battery was connected to VIN terminal
- USB voltage (~5.0V) vs battery voltage (~5.0V) was ambiguous
- Power selector likely split between both sources
- INA238 on motor rail saw near-zero current despite motor operation

This is the same symptom, same root cause, same class of problem as the USB-C non-isolation finding on the Pi 5 ([docs/power-architecture.md](../power-architecture.md)).

**Both symptoms are instances of a general pattern:** boards with multiple OR'd power inputs create unexpected current paths that bypass in-line current sensors.

## Action Items

### Immediate (this session)

- [x] Save validated test harness to `scripts/bench/`
- [x] Document findings in this file
- [ ] Apply fix to main robot counter-drive setup: raise motor battery voltage OR disconnect USB during motor tests
- [ ] Update [docs/RUNBOOK.md](../RUNBOOK.md) with pre-flight check: "verify motor battery voltage > USB voltage before current-sense tests"

### Follow-up (future sessions)

- [ ] Test INA238 on actual robot motor rail with battery voltage raised
- [ ] Document same-class behavior for all OR'd-power inputs: Pi 5 USB-C vs GPIO, Maker Pi RP2040 USB vs VIN, Robo Pico USB vs VIN vs LiPo
- [ ] Consider hardware mod: Schottky diode on USB VBUS input of motor controller boards to force battery-dominance
- [ ] Counter-drive session resumes with verified current visibility

## Reference Material

- Cytron Robo Pico Datasheet Rev 1.0 (April 2023) — Section 6 Power Tree
- TI INA237 datasheet SBOSA20C (INA237/238 register-identical)
- Cytron Maker Pi RP2040 Datasheet Rev 1.2 (January 2022)
- This session's test output: 14 pulse captures showing consistent inrush profile
- Related: [docs/notes/counter-drive-session-handoff.md](../notes/counter-drive-session-handoff.md)

## Implications for Counter-Drive

With INA238 validated as working, the counter-drive session can resume provided the power-path issue is addressed. Options:

1. **Raise motor battery voltage** to 6V+ (this session's approach on bench)
2. **Disconnect USB from Maker Pi RP2040** during motor tests (loses serial bridge telemetry)
3. **Add hardware Schottky diode** on USB VBUS input (permanent fix)
4. **Accept no current visibility and remove `I_FAULT_THRESHOLD` from FSM** (defense-in-depth without current sensor, as previously proposed in counter-drive session)

Option 4 remains a viable fallback if the power-path workarounds prove inconvenient. The other safety layers (HW watchdog, encoder-gated termination, 15% PWM cap, shared abort) are independently sufficient for bench-test safety.