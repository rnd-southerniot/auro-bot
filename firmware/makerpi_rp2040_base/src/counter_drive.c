#include "counter_drive.h"

#include <math.h>
#include <stddef.h>

#include "pico/stdlib.h"
#include "pico/time.h"

#include "config.h"
#include "wheel.h"

/*
 * Shared abort: set by any motor that enters FAULT. Checked by both
 * motors on every CD tick. Cleared by counter_drive_reset() only when
 * both motors are in non-FAULT states (otherwise clearing would let a
 * still-faulted motor continue).
 *
 * volatile: written from an ISR (watchdog alarm callback) and read from
 * the main-loop tick context.
 */
static volatile bool counter_drive_shared_abort = false;

/* Alarm-callback bridge: the SDK alarm callback cannot take a non-POD
 * argument, so we park pointers to both motor structs here. Set up at
 * _init() time when both motors register. Either may be NULL if only
 * one is registered (not expected in production). */
static cd_motor_t *cd_motors[2] = { NULL, NULL };
static uint8_t cd_motor_count = 0;

/* Forward decls --------------------------------------------------- */

static int64_t counter_drive_watchdog_cb(alarm_id_t id, void *user_data);
static void cd_arm_watchdog(cd_motor_t *cdm);
static void cd_disarm_watchdog(cd_motor_t *cdm);
static void cd_cut_pwm(cd_motor_t *cdm);
static void cd_enter_fault(cd_motor_t *cdm, cd_fault_t reason);
static float cd_wheel_speed_mms(const cd_motor_t *cdm);

/* Utility --------------------------------------------------------- */

static uint32_t now_ms(void) {
    return to_ms_since_boot(get_absolute_time());
}

static float cd_wheel_speed_mms(const cd_motor_t *cdm) {
    /* wheel_cps_to_mps returns m/s (signed); convert to signed mm/s. */
    float mps = wheel_cps_to_mps(cdm->wheel, cdm->wheel->speed_filtered);
    return mps * 1000.0f;
}

static int8_t sign_f(float v) {
    if (v > 0.0f) return 1;
    if (v < 0.0f) return -1;
    return 0;
}

static float fabsf_local(float v) {
    return v < 0.0f ? -v : v;
}

/* PWM routing ----------------------------------------------------- */

static void cd_cut_pwm(cd_motor_t *cdm) {
    /* TODO: extract dedicated wheel_apply_counter_drive_pwm() in cleanup
     * session -- semantic clarity, not blocking. */
    wheel_apply_test_pwm(cdm->wheel, 0);
    cdm->current_pwm = 0;
}

static void cd_apply_reverse(cd_motor_t *cdm, int8_t entry_direction) {
    int16_t pwm = -(int16_t)entry_direction * (int16_t)COUNTER_DRIVE_PWM_MAX;
    /* TODO: extract dedicated wheel_apply_counter_drive_pwm() in cleanup
     * session -- semantic clarity, not blocking. */
    wheel_apply_test_pwm(cdm->wheel, pwm);
    cdm->current_pwm = pwm;
}

/* HW watchdog ----------------------------------------------------- */

/* Alarm callback runs in ISR-like context; keep it minimal.
 * Cuts PWM on both motors and transitions the faulted motor to FAULT
 * via the shared_abort path (the FSM tick handles the transition on
 * the next 10 ms control tick).
 */
static int64_t counter_drive_watchdog_cb(alarm_id_t id, void *user_data) {
    (void)id;
    cd_motor_t *cdm = (cd_motor_t *)user_data;
    if (cdm == NULL) return 0;

    /* Hard-cut PWM immediately. This bypasses the FSM because waiting
     * 10 ms for the next tick is too long at 15% duty pulse magnitudes
     * with potentially degraded encoder feedback. */
    wheel_apply_test_pwm(cdm->wheel, 0);
    cdm->current_pwm = 0;

    /* Also cut the peer motor if we have it registered. */
    for (uint8_t i = 0; i < cd_motor_count; i++) {
        cd_motor_t *peer = cd_motors[i];
        if (peer != NULL && peer != cdm) {
            wheel_apply_test_pwm(peer->wheel, 0);
            peer->current_pwm = 0;
        }
    }

    /* Mark fault; the next tick will see this and transition to FAULT. */
    cdm->last_fault = CD_FAULT_WATCHDOG;
    counter_drive_shared_abort = true;

    /* 0 = do not reschedule. */
    return 0;
}

static void cd_arm_watchdog(cd_motor_t *cdm) {
    /* add_alarm_in_ms returns alarm_id > 0 on success, <= 0 on failure
     * (pool full or immediate firing). We store the id for later cancel. */
    cdm->watchdog_alarm_id = add_alarm_in_ms(
        COUNTER_DRIVE_MAX_DURATION_MS,
        counter_drive_watchdog_cb,
        cdm,
        /* fire_if_past = */ true
    );
}

static void cd_disarm_watchdog(cd_motor_t *cdm) {
    if (cdm->watchdog_alarm_id > 0) {
        cancel_alarm((alarm_id_t)cdm->watchdog_alarm_id);
    }
    cdm->watchdog_alarm_id = -1;
}

/* Fault entry ----------------------------------------------------- */

static void cd_enter_fault(cd_motor_t *cdm, cd_fault_t reason) {
    cd_cut_pwm(cdm);
    cd_disarm_watchdog(cdm);
    cdm->last_fault = reason;
    cdm->state = CD_STATE_FAULT;
    cdm->debounce_ticks = 0;
    cdm->stop_ticks = 0;
    counter_drive_shared_abort = true;
}

/* Public API ------------------------------------------------------ */

void counter_drive_init(cd_motor_t *cdm, wheel_t *w) {
    cdm->wheel = w;
    cdm->state = CD_STATE_IDLE;
    cdm->last_fault = CD_FAULT_NONE;
    cdm->entry_direction = 0;
    cdm->entry_speed_cps = 0.0f;
    cdm->entry_ms = 0;
    cdm->debounce_ticks = 0;
    cdm->stop_ticks = 0;
    cdm->current_pwm = 0;
    cdm->watchdog_alarm_id = -1;

    /* Register for the shared-abort callback's peer-cut routing. */
    if (cd_motor_count < 2) {
        cd_motors[cd_motor_count++] = cdm;
    }
}

void counter_drive_reset(cd_motor_t *cdm) {
    cd_cut_pwm(cdm);
    cd_disarm_watchdog(cdm);
    cdm->state = CD_STATE_IDLE;
    cdm->last_fault = CD_FAULT_NONE;
    cdm->debounce_ticks = 0;
    cdm->stop_ticks = 0;
    cdm->entry_direction = 0;
    cdm->entry_speed_cps = 0.0f;
    cdm->entry_ms = 0;

    /* Clear shared_abort only if BOTH motors are non-FAULT. Otherwise
     * the still-faulted motor's semantics are preserved. */
    bool all_clear = true;
    for (uint8_t i = 0; i < cd_motor_count; i++) {
        if (cd_motors[i] != NULL && cd_motors[i]->state == CD_STATE_FAULT) {
            all_clear = false;
            break;
        }
    }
    if (all_clear) {
        counter_drive_shared_abort = false;
    }
}

void counter_drive_tick(cd_motor_t *cdm) {
#if !COUNTER_DRIVE_ENABLED
    (void)cdm;
    return;
#else
    /* Derive motion-desired from the wheel's own mode rather than from
     * top-level motion_cmd_active. This is robust to COMMAND_TIMEOUT
     * transitions (which set wheel to IDLE) and to explicit STOP/ESTOP. */
    bool motion_desired = (cdm->wheel->mode == WMODE_SPEED);

    float speed_mms = cd_wheel_speed_mms(cdm);
    float speed_abs_mms = fabsf_local(speed_mms);

    switch (cdm->state) {

    case CD_STATE_IDLE:
        if (motion_desired) {
            cdm->state = CD_STATE_NORMAL;
        }
        break;

    case CD_STATE_NORMAL:
        if (!motion_desired) {
            cdm->state = CD_STATE_DECEL_MON;
            cdm->debounce_ticks = 0;
        }
        break;

    case CD_STATE_DECEL_MON:
        if (motion_desired) {
            cdm->state = CD_STATE_NORMAL;
            cdm->debounce_ticks = 0;
            break;
        }
        cdm->debounce_ticks++;
        if (cdm->debounce_ticks >= COUNTER_DRIVE_DEBOUNCE_TICKS) {
            if (speed_abs_mms >= (float)COUNTER_DRIVE_MIN_ACTIVATION_MMS) {
                /* Capture entry state, arm watchdog, apply reverse PWM. */
                cdm->entry_direction = sign_f(speed_mms);
                cdm->entry_speed_cps = fabsf_local(cdm->wheel->speed_filtered);
                cdm->entry_ms = now_ms();
                cdm->stop_ticks = 0;
                cdm->state = CD_STATE_ACTIVE;
                cd_arm_watchdog(cdm);
                cd_apply_reverse(cdm, cdm->entry_direction);
            } else {
                /* Already essentially stopped; skip active CD. */
                cdm->state = CD_STATE_IDLE;
                cdm->debounce_ticks = 0;
            }
        }
        break;

    case CD_STATE_ACTIVE:
        /* Shared abort: a peer motor faulted. Quiet exit. */
        if (counter_drive_shared_abort && cdm->last_fault == CD_FAULT_NONE) {
            cd_cut_pwm(cdm);
            cd_disarm_watchdog(cdm);
            cdm->last_fault = CD_FAULT_SHARED_ABORT;
            cdm->state = CD_STATE_IDLE;
            break;
        }

        /* Our own watchdog fired in the ISR; state machine catches up. */
        if (cdm->last_fault == CD_FAULT_WATCHDOG) {
            cdm->state = CD_STATE_FAULT;
            break;
        }

        /* Velocity anomaly: growing in entry direction beyond tolerance. */
        {
            float entry_mag = cdm->entry_speed_cps;
            float now_mag = fabsf_local(cdm->wheel->speed_filtered);
            int8_t now_dir = sign_f(cdm->wheel->speed_filtered);
            bool same_dir = (now_dir == cdm->entry_direction && now_dir != 0);
            bool grew = (now_mag > entry_mag * COUNTER_DRIVE_ANOMALY_GROWTH_FACTOR);
            if (same_dir && grew) {
                cd_enter_fault(cdm, CD_FAULT_ANOMALY);
                break;
            }
        }

        /* Encoder-gated termination. */
        if (speed_abs_mms < (float)COUNTER_DRIVE_V_STOP_MMS) {
            cdm->stop_ticks++;
            if (cdm->stop_ticks >= COUNTER_DRIVE_N_STOP_TICKS) {
                cd_cut_pwm(cdm);
                cd_disarm_watchdog(cdm);
                cdm->state = CD_STATE_IDLE;
                cdm->stop_ticks = 0;
            }
        } else {
            cdm->stop_ticks = 0;
        }
        break;

    case CD_STATE_FAULT:
        /* Belt-and-suspenders: ensure PWM stays at 0 while latched. */
        cd_cut_pwm(cdm);
        break;

    default:
        /* Unknown state -- force to IDLE and clear applied PWM. */
        cd_cut_pwm(cdm);
        cdm->state = CD_STATE_IDLE;
        break;
    }
#endif  /* COUNTER_DRIVE_ENABLED */
}

/* Telemetry helpers ----------------------------------------------- */

uint8_t cd_state_wire(cd_state_t s) {
    return (uint8_t)s;
}

uint8_t cd_fault_wire(cd_fault_t f) {
    return (uint8_t)f;
}

uint32_t cd_duration_ms(const cd_motor_t *cdm) {
    if (cdm->state != CD_STATE_ACTIVE) return 0;
    uint32_t n = now_ms();
    return (n >= cdm->entry_ms) ? (n - cdm->entry_ms) : 0;
}
