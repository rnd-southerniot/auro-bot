#include "wheel.h"

#include <assert.h>
#include <math.h>

#include "hardware/gpio.h"
#include "hardware/clocks.h"
#include "hardware/pio.h"
#include "hardware/pwm.h"

#include "config.h"
#include "quadrature_encoder.pio.h"
#include "safety.h"

static const int8_t QUAD_TABLE[16] = {
     0, -1, +1,  0,
    +1,  0,  0, -1,
    -1,  0,  0, +1,
     0, +1, -1,  0
};

static uint pio_prog_offset;
static bool pio_prog_loaded = false;
static const float PI_F = 3.14159265358979323846f;

static void wheel_motor_coast(wheel_t *w) {
    pwm_set_chan_level(w->pwm_slice, PWM_CHAN_A, 0);
    pwm_set_chan_level(w->pwm_slice, PWM_CHAN_B, 0);
}

static int16_t wheel_slew_duty(int16_t current, int16_t target) {
    int16_t delta = target - current;

    if (delta > MOTOR_DUTY_SLEW_PER_TICK) {
        return current + MOTOR_DUTY_SLEW_PER_TICK;
    }
    if (delta < -MOTOR_DUTY_SLEW_PER_TICK) {
        return current - MOTOR_DUTY_SLEW_PER_TICK;
    }
    return target;
}

static void wheel_motor_set(wheel_t *w, int16_t power) {
    uint ch_fwd = w->swap_dir ? PWM_CHAN_B : PWM_CHAN_A;
    uint ch_rev = w->swap_dir ? PWM_CHAN_A : PWM_CHAN_B;

    if (safety_is_faulted()) {
        wheel_motor_coast(w);
        w->duty = 0;
        return;
    }

    if (power > MOTOR_MAX_DUTY) {
        power = MOTOR_MAX_DUTY;
    }
    if (power < -MOTOR_MAX_DUTY) {
        power = -MOTOR_MAX_DUTY;
    }

    if (power > 0) {
        pwm_set_chan_level(w->pwm_slice, ch_rev, 0);
        pwm_set_chan_level(w->pwm_slice, ch_fwd, (uint16_t)power);
    } else if (power < 0) {
        pwm_set_chan_level(w->pwm_slice, ch_fwd, 0);
        pwm_set_chan_level(w->pwm_slice, ch_rev, (uint16_t)(-power));
    } else {
        wheel_motor_coast(w);
    }

    if (safety_is_faulted()) {
        wheel_motor_coast(w);
        w->duty = 0;
    }
}

void wheel_init(
    wheel_t *w,
    const char *name,
    uint pin_fwd,
    uint pin_rev,
    PIO pio,
    uint sm,
    uint enc_pin_a,
    int32_t counts_per_rev,
    float wheel_radius_m,
    bool swap_dir
) {
    const float pwm_clk_hz = (float)clock_get_hz(clk_sys);
    float pwm_clkdiv = pwm_clk_hz / ((float)MOTOR_PWM_FREQ_HZ * (float)(MOTOR_PWM_WRAP + 1));

    w->name = name;
    w->pio = pio;
    w->sm = sm;
    w->pin_fwd = pin_fwd;
    w->pin_rev = pin_rev;
    w->swap_dir = swap_dir;
    w->enc_count = 0;
    w->prev_count = 0;
    w->counts_per_rev = counts_per_rev;
    w->wheel_radius_m = wheel_radius_m;
    w->speed_filtered = 0.0f;
    w->speed_setpoint_cps = 0.0f;
    w->mode = WMODE_IDLE;
    w->duty = 0;
    w->stall_timer_ms = 0;
    w->stall_inhibit_ms = 0;

    gpio_set_function(pin_fwd, GPIO_FUNC_PWM);
    gpio_set_function(pin_rev, GPIO_FUNC_PWM);
    w->pwm_slice = pwm_gpio_to_slice_num(pin_fwd);
    assert(pwm_gpio_to_slice_num(pin_fwd) == pwm_gpio_to_slice_num(pin_rev));
    if (pwm_clkdiv < 1.0f) {
        pwm_clkdiv = 1.0f;
    }
    if (pwm_clkdiv > 255.0f) {
        pwm_clkdiv = 255.0f;
    }
    pwm_set_clkdiv(w->pwm_slice, pwm_clkdiv);
    pwm_set_wrap(w->pwm_slice, MOTOR_PWM_WRAP);
    pwm_set_chan_level(w->pwm_slice, PWM_CHAN_A, 0);
    pwm_set_chan_level(w->pwm_slice, PWM_CHAN_B, 0);
    pwm_set_enabled(w->pwm_slice, true);

    if (!pio_prog_loaded) {
        pio_prog_offset = pio_add_program(pio, &quadrature_encoder_program);
        pio_prog_loaded = true;
    }

    quadrature_encoder_program_init(pio, sm, pio_prog_offset, enc_pin_a);

    pid_init(
        &w->speed_pid,
        SPEED_KP_DEFAULT,
        SPEED_KI_DEFAULT,
        SPEED_KD_DEFAULT,
        SPEED_OUTPUT_MIN,
        SPEED_OUTPUT_MAX,
        PID_INTEGRAL_MAX
    );
}

void wheel_encoder_update(wheel_t *w) {
    while (!pio_sm_is_rx_fifo_empty(w->pio, w->sm)) {
        uint32_t transition = pio_sm_get(w->pio, w->sm);
        int8_t delta = QUAD_TABLE[transition & 0x0F];
        w->enc_count += w->swap_dir ? -delta : delta;
    }
}

void wheel_encoder_zero(wheel_t *w) {
    wheel_encoder_update(w);
    w->enc_count = 0;
    w->prev_count = 0;
    w->speed_filtered = 0.0f;
}

float wheel_mps_to_cps(const wheel_t *w, float mps) {
    float circumference = 2.0f * PI_F * w->wheel_radius_m;
    if (circumference <= 0.0f) {
        return 0.0f;
    }
    return (mps / circumference) * (float)w->counts_per_rev;
}

float wheel_cps_to_mps(const wheel_t *w, float cps) {
    return cps * ((2.0f * PI_F * w->wheel_radius_m) / (float)w->counts_per_rev);
}

void wheel_set_speed_cps(wheel_t *w, float cps) {
    if (fabsf(cps) <= STOP_SETPOINT_CPS_DEADBAND) {
        wheel_stop(w);
        return;
    }

    float previous_cps = w->speed_setpoint_cps;
    if (w->mode != WMODE_SPEED) {
        pid_reset(&w->speed_pid);
    }
    if (
        w->mode != WMODE_SPEED ||
        fabsf(cps - previous_cps) >= STALL_SETPOINT_CHANGE_CPS
    ) {
        w->stall_timer_ms = 0;
        w->stall_inhibit_ms = STALL_STARTUP_GRACE_MS;
    }
    w->speed_setpoint_cps = cps;
    w->mode = WMODE_SPEED;
}

void wheel_set_speed_mps(wheel_t *w, float mps) {
    wheel_set_speed_cps(w, wheel_mps_to_cps(w, mps));
}

void wheel_stop(wheel_t *w) {
    w->speed_setpoint_cps = 0.0f;
    w->duty = 0;
    w->stall_timer_ms = 0;
    w->stall_inhibit_ms = 0;
    pid_reset(&w->speed_pid);
    wheel_motor_coast(w);
    w->mode = WMODE_IDLE;
}

void wheel_apply_test_pwm(wheel_t *w, int16_t duty) {
    /*
     * Bench/test hook that bypasses PID and velocity setpoint.
     *
     * Force mode to IDLE so wheel_tick() will not touch the PWM channels
     * on the next control tick. Clear PID and stall bookkeeping so that
     * when the test pulse finishes and normal drive resumes, there is no
     * stale state (wound-up integral, stall accumulator) carried over.
     *
     * wheel_motor_set() already bounds |duty| to MOTOR_MAX_DUTY and
     * forces coast on safety fault, so this wrapper does not need to
     * duplicate those checks.
     */
    w->mode = WMODE_IDLE;
    w->speed_setpoint_cps = 0.0f;
    w->stall_timer_ms = 0;
    w->stall_inhibit_ms = 0;
    pid_reset(&w->speed_pid);
    wheel_motor_set(w, duty);
    w->duty = duty;
}

bool wheel_tick(wheel_t *w, float dt) {
    wheel_encoder_update(w);

    int64_t count = w->enc_count;
    int64_t delta = count - w->prev_count;
    float raw_cps = 0.0f;

    if (dt > 0.0f) {
        raw_cps = (float)delta / dt;
    }
    w->prev_count = count;
    w->speed_filtered = (SPEED_FILTER_ALPHA * raw_cps) + ((1.0f - SPEED_FILTER_ALPHA) * w->speed_filtered);

    if (w->mode == WMODE_SPEED) {
        float duty_cmd = pid_update(&w->speed_pid, w->speed_setpoint_cps, w->speed_filtered, dt);
        w->duty = wheel_slew_duty(w->duty, (int16_t)duty_cmd);
        wheel_motor_set(w, w->duty);
    }

    int16_t abs_duty = (w->duty < 0) ? -w->duty : w->duty;
    int64_t abs_delta = (delta < 0) ? -delta : delta;
    uint32_t tick_ms = CONTROL_LOOP_PERIOD_US / 1000;

    if (w->stall_inhibit_ms > 0) {
        if (w->stall_inhibit_ms > tick_ms) {
            w->stall_inhibit_ms -= tick_ms;
        } else {
            w->stall_inhibit_ms = 0;
        }
        w->stall_timer_ms = 0;
        return false;
    }

    if (w->mode == WMODE_SPEED && abs_duty > STALL_DUTY_THRESHOLD && abs_delta < STALL_DELTA_THRESHOLD) {
        w->stall_timer_ms += tick_ms;
        if (w->stall_timer_ms >= STALL_TIMEOUT_MS) {
            return true;
        }
    } else {
        w->stall_timer_ms = 0;
    }

    return false;
}

bool wheel_is_active(const wheel_t *w) {
    return w->mode != WMODE_IDLE;
}

const char *wheel_mode_name(wheel_mode_t mode) {
    switch (mode) {
        case WMODE_IDLE:  return "IDLE";
        case WMODE_SPEED: return "SPEED";
        default:          return "UNKNOWN";
    }
}
