"""
INA238 + Motor bench test on Cytron Robo Pico + Pico 2W

PURPOSE
-------
Isolated bench instrument for validating INA238 current-sense telemetry
during motor operation. Used to diagnose the "INA238 reads zero" symptom
during counter-drive session relocation work (2026-04-20).

VALIDATION RESULTS (2026-04-20, lifted-wheel test)
--------------------------------------------------
Idle:    VBUS = 6.23V, Current = 18.6 mA (Pico+board logic only)
Pulse:   Peak inrush = 145-151 mA, steady = 60-80 mA at 30% PWM
Shunt:   0.9-2.3 mV during pulse, noise floor ~0.28 mV at idle
Result:  INA238 chip + shunt wiring fully functional

KEY FINDING
-----------
Robo Pico's Multiple Power Input Selector (see datasheet section 6) picks
the highest voltage input between USB, VIN, and LiPo. If USB and battery
voltages are close (e.g. USB 5.1V, battery 5.17V), power splits between
them and most motor current flows via USB, bypassing the shunt.

Solution: ensure motor battery voltage clearly exceeds USB voltage. At
6.2V+ battery vs 5.1V USB, battery wins cleanly and all motor current
flows through the INA238 shunt as expected.

This same behavior applies to Maker Pi RP2040 on the main robot.

HARDWARE
--------
- Cytron Robo Pico with Raspberry Pi Pico 2W socketed
- INA238 breakout on Maker Port (I²C1: SDA=GP2, SCL=GP3, addr 0x40)
  - VIN+ to motor battery positive
  - VIN- to Robo Pico VIN terminal
  - VBUS jumper CLOSED (high-side sensing, reads battery voltage)
  - VS from Pico 3V3 (via STEMMA QT cable)
- One DC motor on M1 terminals (M1A=GP8, M1B=GP9)
- Motor battery 5.5-6V (must be clearly above USB voltage)

BUTTONS
-------
- GP20: START — 500ms forward pulse at 30% PWM
- GP21: STOP  — immediate brake

USAGE
-----
1. Copy to Pico as main.py (or run via Thonny)
2. Open serial console at 115200 baud
3. Verify INA238 init passes all checks on boot
4. Press GP20 to trigger pulse, observe current telemetry
5. Press GP21 for emergency stop any time

EXPECTED CURRENT PROFILE (healthy, lifted wheel, 30% PWM)
---------------------------------------------------------
t=0ms       Pulse starts, inrush begins
t=100ms     Peak ~150 mA (motor accelerating)
t=200ms+    Steady state 60-80 mA (no-load coast)
t=500ms     Pulse ends, auto-brake

References:
  - TI INA237 datasheet SBOSA20C (INA237/238 register-identical)
  - Cytron Robo Pico datasheet Rev 1.0 (April 2023)
  - Southern IoT claude-navbot repo, docs/testing/ina238-bench-validation.md
"""

from machine import Pin, I2C, PWM
import time
import struct

# ---------- INA238 Configuration ----------
INA238_ADDR = 0x40

REG_CONFIG           = 0x00
REG_ADC_CONFIG       = 0x01
REG_SHUNT_CAL        = 0x02
REG_VSHUNT           = 0x04
REG_VBUS             = 0x05
REG_DIETEMP          = 0x06
REG_CURRENT          = 0x07
REG_POWER            = 0x08
REG_DIAG_ALRT        = 0x0B
REG_MFG_ID           = 0x3E
REG_DEVICE_ID        = 0x3F

SHUNT_OHMS           = 0.015   # 15 mΩ on-board shunt (Adafruit INA238 breakout)
MAX_EXPECTED_CURRENT = 2.0     # 2A max — safe vs 1.5A per-channel peak rating
ADCRANGE             = 1       # 1 = ±40.96 mV range (better resolution)

CURRENT_LSB = MAX_EXPECTED_CURRENT / 32768.0
SHUNT_CAL_VALUE = int(819.2e6 * CURRENT_LSB * SHUNT_OHMS * (4 if ADCRANGE else 1))

# ADC_CONFIG: continuous bus+shunt+temp, 1052µs conversion, averaging=4
ADC_CONFIG_VALUE = (0xF << 12) | (0x5 << 9) | (0x5 << 6) | (0x5 << 3) | 0x1

CONFIG_VALUE = (ADCRANGE & 0x1) << 4

# ---------- Motor PWM Configuration ----------
MOTOR_A_PIN = 8   # GP8 = M1A (Forward PWM)
MOTOR_B_PIN = 9   # GP9 = M1B (Backward PWM)
PWM_FREQ    = 20000  # 20 kHz per Cytron datasheet
PWM_FORWARD_DUTY = 30

# ---------- Buttons ----------
BUTTON_START_PIN = 20
BUTTON_STOP_PIN  = 21

# ---------- Pulse Timing ----------
PULSE_DURATION_MS = 500

# ---------- Globals ----------
i2c = None
motor_a = None
motor_b = None
button_start = None
button_stop  = None
peak_current_mA = 0
pulse_active = False
pulse_start_ms = 0


# ========== INA238 Driver ==========

def write_reg(reg, value):
    data = bytes([(value >> 8) & 0xFF, value & 0xFF])
    i2c.writeto_mem(INA238_ADDR, reg, data)

def read_reg(reg):
    data = i2c.readfrom_mem(INA238_ADDR, reg, 2)
    return (data[0] << 8) | data[1]

def read_reg_signed(reg):
    raw = read_reg(reg)
    return struct.unpack('>h', struct.pack('>H', raw))[0]

def read_reg_24(reg):
    data = i2c.readfrom_mem(INA238_ADDR, reg, 3)
    return (data[0] << 16) | (data[1] << 8) | data[2]

def ina238_init():
    try:
        mfg_id = read_reg(REG_MFG_ID)
        device_id = read_reg(REG_DEVICE_ID)

        print(f"[INA238] MANUFACTURER_ID (0x3E): 0x{mfg_id:04X}", end="")
        print(f"  {'OK (TI)' if mfg_id == 0x5449 else 'WRONG'}")
        print(f"[INA238] DEVICE_ID (0x3F):       0x{device_id:04X}", end="")
        print(f"  {'OK (INA238 rev B)' if device_id == 0x2381 else '(unknown rev)'}")

        if mfg_id != 0x5449:
            print("[INA238] FATAL: wrong manufacturer ID, aborting init")
            return False

        write_reg(REG_CONFIG, CONFIG_VALUE)
        config_readback = read_reg(REG_CONFIG)
        print(f"[INA238] CONFIG wrote 0x{CONFIG_VALUE:04X}, read 0x{config_readback:04X}", end="")
        print(f"  {'OK' if config_readback == CONFIG_VALUE else 'FAIL'}")

        write_reg(REG_ADC_CONFIG, ADC_CONFIG_VALUE)
        adc_readback = read_reg(REG_ADC_CONFIG)
        print(f"[INA238] ADC_CONFIG wrote 0x{ADC_CONFIG_VALUE:04X}, read 0x{adc_readback:04X}", end="")
        print(f"  {'OK' if adc_readback == ADC_CONFIG_VALUE else 'FAIL'}")

        write_reg(REG_SHUNT_CAL, SHUNT_CAL_VALUE)
        cal_readback = read_reg(REG_SHUNT_CAL)
        print(f"[INA238] SHUNT_CAL wrote {SHUNT_CAL_VALUE} (0x{SHUNT_CAL_VALUE:04X})", end="")
        print(f", read {cal_readback}  {'OK' if cal_readback == SHUNT_CAL_VALUE else 'FAIL'}")

        print(f"[INA238] CURRENT_LSB = {CURRENT_LSB*1e6:.2f} uA/bit")
        print(f"[INA238] Expected at 300 mA load: CURRENT register = {int(0.3/CURRENT_LSB)}")
        print(f"[INA238] Expected shunt voltage at 300 mA: {0.3 * SHUNT_OHMS * 1000:.2f} mV")
        print(f"[INA238] Init complete.")
        return True

    except Exception as e:
        print(f"[INA238] Init error: {e}")
        return False

def read_measurements():
    try:
        vshunt_raw = read_reg_signed(REG_VSHUNT)
        vbus_raw   = read_reg(REG_VBUS)
        dietemp_raw = read_reg_signed(REG_DIETEMP) >> 4
        current_raw = read_reg_signed(REG_CURRENT)
        power_raw   = read_reg_24(REG_POWER)

        shunt_lsb = 1.25e-6 if ADCRANGE else 5e-6
        shunt_v   = vshunt_raw * shunt_lsb
        bus_v     = vbus_raw * 3.125e-3
        temp_c    = dietemp_raw * 0.125
        current_a = current_raw * CURRENT_LSB
        power_w   = power_raw * (0.2 * CURRENT_LSB)

        return {
            'vshunt_mv': shunt_v * 1000,
            'vbus_v': bus_v,
            'current_ma': current_a * 1000,
            'power_mw': power_w * 1000,
            'temp_c': temp_c,
            'current_raw': current_raw,
            'vshunt_raw': vshunt_raw,
        }
    except Exception as e:
        return {'error': str(e)}


# ========== Motor Control ==========

def motor_init():
    global motor_a, motor_b
    motor_a = PWM(Pin(MOTOR_A_PIN))
    motor_b = PWM(Pin(MOTOR_B_PIN))
    motor_a.freq(PWM_FREQ)
    motor_b.freq(PWM_FREQ)
    motor_a.duty_u16(0)
    motor_b.duty_u16(0)

def motor_forward(duty_percent):
    duty = int((duty_percent / 100.0) * 65535)
    motor_a.duty_u16(duty)
    motor_b.duty_u16(0)

def motor_brake():
    motor_a.duty_u16(0)
    motor_b.duty_u16(0)

def motor_coast():
    motor_a.duty_u16(65535)
    motor_b.duty_u16(65535)


# ========== Main Loop ==========

def main():
    global i2c, button_start, button_stop
    global pulse_active, pulse_start_ms, peak_current_mA

    print("=" * 60)
    print("INA238 + Motor Test on Robo Pico + Pico 2W")
    print("=" * 60)

    i2c = I2C(1, sda=Pin(2), scl=Pin(3), freq=400_000)
    devices = i2c.scan()
    print(f"[I2C] scan: {[hex(d) for d in devices]}")
    if 0x40 not in devices:
        print("[FATAL] INA238 not detected at 0x40. Check wiring. Halting.")
        return

    if not ina238_init():
        print("[FATAL] INA238 init failed. Halting.")
        return

    motor_init()
    print(f"[MOTOR] initialized: M1A=GP{MOTOR_A_PIN}, M1B=GP{MOTOR_B_PIN}, {PWM_FREQ} Hz")

    button_start = Pin(BUTTON_START_PIN, Pin.IN, Pin.PULL_UP)
    button_stop  = Pin(BUTTON_STOP_PIN,  Pin.IN, Pin.PULL_UP)
    print(f"[BUTTONS] START=GP{BUTTON_START_PIN}, STOP=GP{BUTTON_STOP_PIN}")

    print()
    print("READY. Press GP20 button to start a 500ms motor pulse at 30% PWM.")
    print("      Press GP21 button to stop the motor (brake).")
    print()

    last_report_ms = 0
    last_start_press_ms = 0
    last_stop_press_ms  = 0
    debounce_ms = 200

    while True:
        now_ms = time.ticks_ms()

        if button_start.value() == 0:
            if time.ticks_diff(now_ms, last_start_press_ms) > debounce_ms and not pulse_active:
                last_start_press_ms = now_ms
                pulse_active = True
                pulse_start_ms = now_ms
                peak_current_mA = 0
                print(f"\n[PULSE START] GP20 pressed. 30% PWM forward for {PULSE_DURATION_MS}ms.")
                motor_forward(PWM_FORWARD_DUTY)

        if button_stop.value() == 0:
            if time.ticks_diff(now_ms, last_stop_press_ms) > debounce_ms:
                last_stop_press_ms = now_ms
                if pulse_active:
                    print(f"[STOP] GP21 pressed - early termination")
                    pulse_active = False
                motor_brake()

        if pulse_active and time.ticks_diff(now_ms, pulse_start_ms) >= PULSE_DURATION_MS:
            motor_brake()
            pulse_active = False
            elapsed = time.ticks_diff(now_ms, pulse_start_ms)
            print(f"[PULSE END] complete after {elapsed}ms. Peak current: {peak_current_mA:.1f} mA")
            print()

        if time.ticks_diff(now_ms, last_report_ms) >= 100:
            last_report_ms = now_ms
            m = read_measurements()
            if 'error' in m:
                print(f"[ERROR reading INA238: {m['error']}]")
            else:
                if pulse_active and abs(m['current_ma']) > peak_current_mA:
                    peak_current_mA = abs(m['current_ma'])

                state = "ACTIVE" if pulse_active else "idle  "
                print(f"[{state}] "
                      f"V={m['vbus_v']:5.2f}V  "
                      f"I={m['current_ma']:+7.1f} mA  "
                      f"P={m['power_mw']:+7.1f} mW  "
                      f"Vshunt={m['vshunt_mv']:+6.3f} mV  "
                      f"T={m['temp_c']:5.2f}C  "
                      f"(raw_i={m['current_raw']:+6d}, raw_vs={m['vshunt_raw']:+6d})")

        time.sleep_ms(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Ctrl-C] Halting. Braking motor.")
        if motor_a and motor_b:
            motor_brake()
    except Exception as e:
        print(f"[FATAL] {e}")
        if motor_a and motor_b:
            motor_brake()
        raise

