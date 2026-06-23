#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <math.h>

#include "hardware/adc.h"
#include "hardware/pwm.h"
#include "hardware/pio.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"

#include "config.h"
#include "counter_drive.h"
#include "navbot_protocol.h"
#include "pins.h"
#include "safety.h"
#include "serial_parser.h"
#include "telemetry.h"
#include "wheel.h"

/*
 * Bench-only TEST_PWM command. Set to 1 to accept the command; 0 to
 * compile it out (parser still accepts syntactically; handler replies
 * with an ERR). Default-on during counter-drive development sessions.
 */
#ifndef TEST_PWM_ENABLED
#define TEST_PWM_ENABLED 1
#endif
#define TEST_PWM_DURATION_MS 1000
#define TEST_PWM_DUTY_MAX    999

typedef enum {
    CONTROL_IDLE = 0,
    CONTROL_CMD_VEL,
    CONTROL_WHEEL_VEL,
    CONTROL_TIMEOUT,
} control_mode_t;

static wheel_t left_wheel;
static wheel_t right_wheel;
static cd_motor_t cd_left;
static cd_motor_t cd_right;
static control_mode_t control_mode = CONTROL_IDLE;

static char cmd_buf[NAVBOT_PROTOCOL_MAX_LINE];
static uint8_t cmd_len = 0;
static uint32_t last_motion_cmd_ms = 0;
static bool motion_cmd_active = false;
static uint32_t last_telem_ms = 0;
static uint32_t last_vbat_ms = 0;

/* 4-sample moving average buffers for ADC smoothing. */
static uint16_t motor_v_buf[VBAT_SMOOTH_SAMPLES];
static uint16_t lidar_v_buf[VBAT_SMOOTH_SAMPLES];
static uint8_t vbat_buf_idx = 0;
static bool vbat_buf_full = false;

#define BUZZER_FREQ_HZ        1000
#define STARTUP_BEEP_ON_MS      80
#define STARTUP_BEEP_GAP_MS     60
#define MOTION_BEEP_MS         100

/* Non-blocking buzzer state. */
static uint buzzer_slice;
static uint buzzer_chan;
static uint32_t buzzer_off_ms = 0;  /* 0 = idle */

static void buzzer_hw_init(void) {
    buzzer_slice = pwm_gpio_to_slice_num(PIN_BUZZER);
    buzzer_chan  = pwm_gpio_to_channel(PIN_BUZZER);
    /* 125 MHz / 125 = 1 MHz tick, wrap for desired frequency. */
    pwm_set_clkdiv(buzzer_slice, 125.0f);
    pwm_set_wrap(buzzer_slice, (125000000 / 125 / BUZZER_FREQ_HZ) - 1);
    pwm_set_chan_level(buzzer_slice, buzzer_chan,
                       (125000000 / 125 / BUZZER_FREQ_HZ) / 2);
}

static void buzzer_on(void) {
    gpio_set_function(PIN_BUZZER, GPIO_FUNC_PWM);
    pwm_set_enabled(buzzer_slice, true);
}

static void buzzer_off(void) {
    pwm_set_enabled(buzzer_slice, false);
    gpio_set_function(PIN_BUZZER, GPIO_FUNC_SIO);
    gpio_set_dir(PIN_BUZZER, GPIO_OUT);
    gpio_put(PIN_BUZZER, 0);
}

/* Start a non-blocking beep for duration_ms. Called from control path. */
static void buzzer_start(uint32_t duration_ms, uint32_t stamp_ms) {
    buzzer_on();
    buzzer_off_ms = stamp_ms + duration_ms;
}

/* Poll from main loop — turns off buzzer when time expires. */
static void buzzer_tick(uint32_t stamp_ms) {
    if (buzzer_off_ms != 0 && stamp_ms >= buzzer_off_ms) {
        buzzer_off();
        buzzer_off_ms = 0;
    }
}

/*
 * Play a short two-beep pattern on the onboard piezo buzzer (GP22).
 * Called once during boot before watchdog_enable() to avoid trip risk.
 * Total blocking time: 220 ms.
 */
static void startup_beep(void) {
    buzzer_hw_init();

    /* Beep 1 */
    buzzer_on();
    sleep_ms(STARTUP_BEEP_ON_MS);
    buzzer_off();

    sleep_ms(STARTUP_BEEP_GAP_MS);

    /* Beep 2 */
    buzzer_on();
    sleep_ms(STARTUP_BEEP_ON_MS);
    buzzer_off();
}

static uint32_t now_ms(void) {
    return to_ms_since_boot(get_absolute_time());
}

static void stop_all(void) {
    wheel_stop(&left_wheel);
    wheel_stop(&right_wheel);
}

/*
 * Reset counter-drive FSM on both motors. Called from STOP / RESET /
 * ESTOP handlers and from control_step()'s fault-entry paths so any
 * latched CD state (including armed watchdog alarms) is cleaned up.
 * Idempotent -- calling on already-IDLE motors is a no-op.
 */
static void reset_counter_drive_both(void) {
    counter_drive_reset(&cd_left);
    counter_drive_reset(&cd_right);
}

static float absf_local(float value) {
    return value < 0.0f ? -value : value;
}

static void poll_encoders(void) {
    wheel_encoder_update(&left_wheel);
    wheel_encoder_update(&right_wheel);
}

static uint16_t read_adc_channel(uint input) {
    adc_select_input(input);
    return adc_read();
}

static void vbat_sample(void) {
    motor_v_buf[vbat_buf_idx] = read_adc_channel(1);  /* ADC1 = GP27 */
    lidar_v_buf[vbat_buf_idx] = read_adc_channel(2);  /* ADC2 = GP28 */
    vbat_buf_idx++;
    if (vbat_buf_idx >= VBAT_SMOOTH_SAMPLES) {
        vbat_buf_idx = 0;
        vbat_buf_full = true;
    }
}

static float vbat_average(const uint16_t *buf) {
    uint8_t count = vbat_buf_full ? VBAT_SMOOTH_SAMPLES : vbat_buf_idx;
    if (count == 0) {
        return 0.0f;
    }
    uint32_t sum = 0;
    for (uint8_t i = 0; i < count; i++) {
        sum += buf[i];
    }
    float adc_v = ((float)sum / (float)count / 4095.0f) * ADC_VREF;
    return adc_v * VDIV_RATIO;
}

static void publish_vbat_telemetry(uint32_t stamp_ms) {
    if ((stamp_ms - last_vbat_ms) < VBAT_INTERVAL_MS) {
        return;
    }
    last_vbat_ms = stamp_ms;
    vbat_sample();
    navbot_telemetry_vbat(stamp_ms, vbat_average(motor_v_buf), vbat_average(lidar_v_buf));
}

static const char *mode_name(void) {
    if (safety_is_faulted()) {
        return safety_get_fault() == SAFETY_ESTOP ? "ESTOP" : "FAULT";
    }

    switch (control_mode) {
        case CONTROL_IDLE:      return "IDLE";
        case CONTROL_CMD_VEL:   return "CMD_VEL";
        case CONTROL_WHEEL_VEL: return "WHEEL_VEL";
        case CONTROL_TIMEOUT:   return "TIMEOUT";
        default:                return "UNKNOWN";
    }
}

static const char *fault_name(void) {
    if (safety_is_faulted()) {
        return safety_fault_name(safety_get_fault());
    }
    if (control_mode == CONTROL_TIMEOUT) {
        return "CMD_TIMEOUT";
    }
    return "OK";
}

static void publish_telemetry(uint32_t stamp_ms) {
    navbot_telemetry_state(mode_name(), fault_name());
    navbot_telemetry_odom(stamp_ms, &left_wheel, &right_wheel);
    navbot_telemetry_cdrive(stamp_ms, &cd_left, &cd_right);
}

static void publish_periodic_telemetry(uint32_t stamp_ms) {
    if ((stamp_ms - last_telem_ms) >= TELEMETRY_INTERVAL_MS) {
        last_telem_ms = stamp_ms;
        publish_telemetry(stamp_ms);
    }
    publish_vbat_telemetry(stamp_ms);
}

static void set_motion_active(control_mode_t mode, uint32_t stamp_ms) {
    /* Short beep on transition from idle/timeout to active motion. */
    if (!motion_cmd_active) {
        buzzer_start(MOTION_BEEP_MS, stamp_ms);
    }
    control_mode = mode;
    last_motion_cmd_ms = stamp_ms;
    motion_cmd_active = true;
}

static void clear_motion_active(control_mode_t mode) {
    motion_cmd_active = false;
    control_mode = mode;
}

static void apply_wheel_targets_mps(float left_mps, float right_mps, control_mode_t mode, uint32_t stamp_ms) {
    wheel_set_speed_mps(&left_wheel, left_mps);
    wheel_set_speed_mps(&right_wheel, right_mps);
    set_motion_active(mode, stamp_ms);
}

static bool validate_cmd_vel(float linear_mps, float angular_rps) {
    if (!isfinite(linear_mps) || !isfinite(angular_rps)) {
        navbot_telemetry_error("BAD_ARGS", "non_finite_velocity");
        return false;
    }
    if (absf_local(linear_mps) > MAX_LINEAR_MPS || absf_local(angular_rps) > MAX_ANGULAR_RPS) {
        navbot_telemetry_error("LIMIT", "cmd_vel_out_of_range");
        return false;
    }
    return true;
}

static bool validate_wheel_targets(float left_mps, float right_mps) {
    if (!isfinite(left_mps) || !isfinite(right_mps)) {
        navbot_telemetry_error("BAD_ARGS", "non_finite_wheel_velocity");
        return false;
    }
    if (absf_local(left_mps) > MAX_WHEEL_MPS || absf_local(right_mps) > MAX_WHEEL_MPS) {
        navbot_telemetry_error("LIMIT", "wheel_velocity_out_of_range");
        return false;
    }
    return true;
}

static void handle_motion_timeout(uint32_t stamp_ms) {
    if (!motion_cmd_active) {
        return;
    }
    if ((stamp_ms - last_motion_cmd_ms) < COMMAND_TIMEOUT_MS) {
        return;
    }

    stop_all();
    clear_motion_active(CONTROL_TIMEOUT);
}

static void handle_command(const navbot_command_t *command, uint32_t stamp_ms) {
    switch (command->type) {
        case NAVBOT_CMD_PING:
            navbot_telemetry_ack_ping();
            break;

        case NAVBOT_CMD_DIAG:
            navbot_telemetry_diag(stamp_ms, &left_wheel, &right_wheel);
            break;

        case NAVBOT_CMD_STOP:
            /*
             * STOP is a SOFT stop that yields to counter-drive. stop_all()
             * puts wheels into IDLE mode; on the next control tick the CD
             * FSM transitions NORMAL -> DECEL_MON -> ACTIVE and applies
             * its reverse-PWM pulse. Do NOT call reset_counter_drive_both()
             * here -- that would short-circuit CD activation (the bug that
             * made tonight's rotation test show no CD firing because the
             * Pi-side bridge sends STOP on every cmd_vel=0, beating the
             * firmware's COMMAND_TIMEOUT_MS race).
             *
             * For immediate hard-cut motor stop, use ESTOP, which both
             * resets CD and latches SAFETY_ESTOP so wheel_motor_set()
             * forces coast on subsequent ticks.
             */
            stop_all();
            clear_motion_active(CONTROL_IDLE);
            navbot_telemetry_ack(command->type);
            break;

        case NAVBOT_CMD_RESET:
            if (!safety_reset()) {
                navbot_telemetry_error("ESTOP_HELD", "release_button_before_reset");
                break;
            }
            stop_all();
            reset_counter_drive_both();
            clear_motion_active(CONTROL_IDLE);
            navbot_telemetry_ack(command->type);
            break;

        case NAVBOT_CMD_ESTOP:
            stop_all();
            reset_counter_drive_both();
            clear_motion_active(CONTROL_IDLE);
            safety_set_fault(SAFETY_ESTOP);
            navbot_telemetry_ack(command->type);
            break;

        case NAVBOT_CMD_CMD_VEL: {
            if (safety_is_faulted()) {
                navbot_telemetry_error("FAULT", safety_fault_name(safety_get_fault()));
                break;
            }
            float linear_mps = command->value_1;
            float angular_rps = command->value_2;
            if (!validate_cmd_vel(linear_mps, angular_rps)) {
                break;
            }
            float half_track = WHEEL_SEPARATION_M * 0.5f;
            float left_mps = linear_mps - (angular_rps * half_track);
            float right_mps = linear_mps + (angular_rps * half_track);
            if (!validate_wheel_targets(left_mps, right_mps)) {
                break;
            }
            apply_wheel_targets_mps(left_mps, right_mps, CONTROL_CMD_VEL, stamp_ms);
            navbot_telemetry_ack(command->type);
            break;
        }

        case NAVBOT_CMD_WHEEL_VEL:
            if (safety_is_faulted()) {
                navbot_telemetry_error("FAULT", safety_fault_name(safety_get_fault()));
                break;
            }
            if (!validate_wheel_targets(command->value_1, command->value_2)) {
                break;
            }
            apply_wheel_targets_mps(command->value_1, command->value_2, CONTROL_WHEEL_VEL, stamp_ms);
            navbot_telemetry_ack(command->type);
            break;

        case NAVBOT_CMD_TEST_PWM: {
#if TEST_PWM_ENABLED
            if (safety_is_faulted()) {
                navbot_telemetry_error("FAULT", safety_fault_name(safety_get_fault()));
                break;
            }
            if (!isfinite(command->value_1) || !isfinite(command->value_2)) {
                navbot_telemetry_error("BAD_ARGS", "non_finite_duty");
                break;
            }
            float left_f  = command->value_1;
            float right_f = command->value_2;
            if (absf_local(left_f)  > (float)TEST_PWM_DUTY_MAX ||
                absf_local(right_f) > (float)TEST_PWM_DUTY_MAX) {
                navbot_telemetry_error("LIMIT", "test_pwm_duty_out_of_range");
                break;
            }
            int16_t left_duty  = (int16_t)left_f;
            int16_t right_duty = (int16_t)right_f;

            /*
             * Cancel any active motion, force both wheels into IDLE so
             * wheel_tick() will not touch PWM, and flush motion-timeout
             * state so handle_motion_timeout() does not fire mid-pulse.
             */
            wheel_stop(&left_wheel);
            wheel_stop(&right_wheel);
            clear_motion_active(CONTROL_IDLE);

            wheel_apply_test_pwm(&left_wheel,  left_duty);
            wheel_apply_test_pwm(&right_wheel, right_duty);

            /*
             * Blocking wait. The outer main loop is stalled, so we pet
             * the HW watchdog (200 ms) and drain encoder PIO FIFOs
             * manually every 50 ms.
             */
            uint32_t start_ms = now_ms();
            while ((now_ms() - start_ms) < TEST_PWM_DURATION_MS) {
                watchdog_update();
                poll_encoders();

                /*
                 * Respect a fault (e.g. ESTOP IRQ) fired mid-pulse by
                 * re-asserting coast immediately and exiting early.
                 * wheel_motor_set() inside wheel_apply_test_pwm already
                 * coasts on fault, but we still break out of the wait.
                 */
                if (safety_is_faulted()) {
                    break;
                }
                sleep_ms(50);
            }

            wheel_apply_test_pwm(&left_wheel,  0);
            wheel_apply_test_pwm(&right_wheel, 0);
            navbot_telemetry_ack(command->type);
#else
            navbot_telemetry_error("DISABLED", "test_pwm_not_compiled_in");
#endif
            break;
        }

        default:
            navbot_telemetry_error("BAD_CMD", "unsupported_command");
            break;
    }
}

static void control_step(float dt, uint32_t stamp_ms) {
    /* Encoder drain happens in the main loop and inside wheel_tick(). */

    if (safety_is_faulted()) {
        stop_all();
        reset_counter_drive_both();
        clear_motion_active(CONTROL_IDLE);
        safety_tick(stamp_ms, false);
        publish_periodic_telemetry(stamp_ms);
        return;
    }

    handle_motion_timeout(stamp_ms);
    bool left_stall = wheel_tick(&left_wheel, dt);
    bool right_stall = wheel_tick(&right_wheel, dt);

    if (left_stall || right_stall) {
        stop_all();
        reset_counter_drive_both();
        clear_motion_active(CONTROL_IDLE);
        safety_set_fault(SAFETY_STALL);
    } else {
        /* Counter-drive runs AFTER wheel_tick so we see fresh
         * speed_filtered and won't fight WMODE_SPEED PWM writes. CD
         * only takes PWM ownership when wheel->mode == WMODE_IDLE. */
        counter_drive_tick(&cd_left);
        counter_drive_tick(&cd_right);
    }

    safety_tick(stamp_ms, wheel_is_active(&left_wheel) || wheel_is_active(&right_wheel));

    publish_periodic_telemetry(stamp_ms);
}

int main(void) {
    stdio_init_all();
    setvbuf(stdout, NULL, _IONBF, 0);

    safety_init();
    startup_beep();
    watchdog_enable(200, true);

    adc_init();
    adc_gpio_init(PIN_ADC_MOTOR_V);
    adc_gpio_init(PIN_ADC_LIDAR_V);

    uint sm_left = pio_claim_unused_sm(pio1, true);
    uint sm_right = pio_claim_unused_sm(pio1, true);

    wheel_init(
        &left_wheel,
        "left",
        PIN_LEFT_FWD,
        PIN_LEFT_REV,
        pio1,
        sm_left,
        PIN_LEFT_ENC_A,
        LEFT_CPR_DEFAULT,
        LEFT_WHEEL_RADIUS_M,
        LEFT_WHEEL_SWAP_DIR
    );

    wheel_init(
        &right_wheel,
        "right",
        PIN_RIGHT_FWD,
        PIN_RIGHT_REV,
        pio1,
        sm_right,
        PIN_RIGHT_ENC_A,
        RIGHT_CPR_DEFAULT,
        RIGHT_WHEEL_RADIUS_M,
        RIGHT_WHEEL_SWAP_DIR
    );

    /* Counter-drive FSMs. Safe whether COUNTER_DRIVE_ENABLED is 0 or 1
     * -- the tick function no-ops when disabled, but init/reset stay
     * active so state is consistent across a compile-flag flip. */
    counter_drive_init(&cd_left,  &left_wheel);
    counter_drive_init(&cd_right, &right_wheel);

    last_telem_ms = now_ms();
    publish_telemetry(last_telem_ms);

    uint64_t last_control_us = time_us_64();

    for (;;) {
        watchdog_update();
        buzzer_tick(now_ms());
        poll_encoders();

        if (!stdio_usb_connected() && motion_cmd_active) {
            stop_all();
            clear_motion_active(CONTROL_IDLE);
        }

        uint64_t current_us = time_us_64();
        if ((current_us - last_control_us) >= CONTROL_LOOP_PERIOD_US) {
            uint64_t elapsed_us = current_us - last_control_us;
            last_control_us = current_us;
            control_step((float)elapsed_us / 1000000.0f, now_ms());
        }

        int c = getchar_timeout_us(0);
        if (c == PICO_ERROR_TIMEOUT) {
            tight_loop_contents();
            continue;
        }

        if (c == '\r') {
            continue;
        }

        if (c == '\n') {
            navbot_command_t command;
            navbot_parse_result_t parse_result;

            cmd_buf[cmd_len] = '\0';
            parse_result = navbot_parse_command_line(cmd_buf, &command);
            cmd_len = 0;

            if (parse_result == NAVBOT_PARSE_EMPTY) {
                continue;
            }
            if (parse_result != NAVBOT_PARSE_OK) {
                navbot_telemetry_error(navbot_parse_result_name(parse_result), "invalid_command_line");
                continue;
            }

            handle_command(&command, now_ms());
            continue;
        }

        if (cmd_len >= (NAVBOT_PROTOCOL_MAX_LINE - 1)) {
            cmd_len = 0;
            navbot_telemetry_error("LINE_TOO_LONG", "input_buffer_overflow");
            continue;
        }

        cmd_buf[cmd_len++] = (char)c;
    }
}
