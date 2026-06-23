#ifndef WHEEL_H
#define WHEEL_H

#include <stdbool.h>
#include <stdint.h>

#include "hardware/pio.h"
#include "pid.h"

typedef enum {
    WMODE_IDLE = 0,
    WMODE_SPEED,
} wheel_mode_t;

typedef struct wheel {
    const char *name;
    PIO pio;
    uint sm;
    uint pwm_slice;
    uint pin_fwd;
    uint pin_rev;
    bool swap_dir;

    volatile int64_t enc_count;
    int64_t prev_count;
    int32_t counts_per_rev;
    float wheel_radius_m;

    float speed_filtered;
    float speed_setpoint_cps;
    pid_ctrl_t speed_pid;

    wheel_mode_t mode;
    int16_t duty;
    uint32_t stall_timer_ms;
    uint32_t stall_inhibit_ms;
} wheel_t;

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
);

bool wheel_tick(wheel_t *w, float dt);
void wheel_set_speed_cps(wheel_t *w, float cps);
void wheel_set_speed_mps(wheel_t *w, float mps);
void wheel_stop(wheel_t *w);

/*
 * Apply a raw signed PWM duty directly to the H-bridge, bypassing the PID
 * and any velocity setpoint. Bench/test use only.
 *
 * Forces the wheel into WMODE_IDLE so wheel_tick() will not overwrite the
 * PWM on the next control tick. The caller is responsible for bounded
 * exposure (e.g. blocking for a known duration, then re-coasting with
 * duty=0). Respects safety_is_faulted() via wheel_motor_set() -- if a
 * fault is latched, motors stay coast.
 *
 * Intended consumers: empirical armature-resistance measurement and
 * counter-drive pulse application. Not used on the normal drive path.
 */
void wheel_apply_test_pwm(wheel_t *w, int16_t duty);

void wheel_encoder_update(wheel_t *w);
void wheel_encoder_zero(wheel_t *w);

float wheel_mps_to_cps(const wheel_t *w, float mps);
float wheel_cps_to_mps(const wheel_t *w, float cps);
bool wheel_is_active(const wheel_t *w);
const char *wheel_mode_name(wheel_mode_t mode);

#endif
