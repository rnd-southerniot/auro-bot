#ifndef COUNTER_DRIVE_H
#define COUNTER_DRIVE_H

#include <stdbool.h>
#include <stdint.h>

/*
 * Counter-drive FSM: applies a bounded reverse-PWM pulse to an individual
 * wheel immediately after cmd_vel -> 0 in order to actively decelerate the
 * drivetrain and shrink coast-on past the commanded stop point.
 *
 * Design and safety properties:
 *   - Per-motor 5-state FSM (IDLE, NORMAL, DECEL_MON, ACTIVE, FAULT).
 *   - Shared abort: any motor FAULT cuts PWM on both motors.
 *   - HW watchdog via default alarm pool: absolute timeout on CD_ACTIVE
 *     pulse duration (COUNTER_DRIVE_MAX_DURATION_MS). If it fires, PWM is
 *     cut and FAULT entered.
 *   - Encoder-gated termination: |speed_filtered| < V_STOP_THRESHOLD_MMS
 *     for N_STOP_TICKS consecutive control ticks -> exit to IDLE.
 *   - Velocity anomaly detection: if speed_filtered grows >20% above the
 *     captured entry magnitude in the same direction as entry (meaning CD
 *     is accelerating the wheel rather than braking it, e.g. sign bug),
 *     enter FAULT and raise shared_abort.
 *   - No firmware current-fault check: the Pi-side INA238 topic publishes
 *     at 2 Hz, far too slow to gate a <=200 ms pulse. Safety is bounded
 *     by PWM cap (15%), HW watchdog, and encoder gating.
 *
 * Compile-time enable: COUNTER_DRIVE_ENABLED (0 default, flipped to 1 in
 * the activation commit after bench validation proves the FSM code path).
 * When disabled, counter_drive_tick() returns immediately; no PWM is
 * ever applied via the CD path.
 *
 * Build dependency: hardware_timer (add to CMakeLists target_link_libraries).
 * Uses the default alarm pool -- verified that no other firmware code
 * uses alarms (grep alarm_pool,hardware_alarm,add_alarm,repeating_timer
 * across src/ and include/ returns nothing).
 */

#ifndef COUNTER_DRIVE_ENABLED
#define COUNTER_DRIVE_ENABLED 1
#endif

/* --- Tunables (hard-coded; see Phase 1 design review 2026-04-20) ------ */

/* Reverse PWM magnitude during CD_ACTIVE. 150 / MOTOR_PWM_WRAP(999) = 15%. */
#define COUNTER_DRIVE_PWM_MAX               150

/* Hard cap on CD_ACTIVE pulse duration. HW watchdog enforces this. */
#define COUNTER_DRIVE_MAX_DURATION_MS       200

/* Ticks of cmd_vel = 0 required before CD can arm. 5 * 10 ms = 50 ms. */
#define COUNTER_DRIVE_DEBOUNCE_TICKS        5

/* mm/s: min |v| at debounce end required to arm CD. Below this we assume
 * the wheel is near-stopped already and skip to IDLE. */
#define COUNTER_DRIVE_MIN_ACTIVATION_MMS    20

/* mm/s: below this magnitude, count a consecutive stop tick toward
 * termination. Chosen 6 mm/s (Phase 1) above the ~5 mm/s single-count
 * encoder noise floor at 100 Hz. */
#define COUNTER_DRIVE_V_STOP_MMS            6

/* Consecutive below-threshold ticks for termination. 3 * 10 ms = 30 ms
 * of hysteresis before we commit to "stopped". */
#define COUNTER_DRIVE_N_STOP_TICKS          3

/* Anomaly: |speed| must not grow more than this factor above entry speed
 * in the same direction as entry. 1.2 = 20% growth tolerance for
 * measurement noise before faulting. */
#define COUNTER_DRIVE_ANOMALY_GROWTH_FACTOR 1.2f

/* --- State / fault enums (wire-stable integer codes for telemetry) --- */

typedef enum {
    CD_STATE_IDLE      = 0,
    CD_STATE_NORMAL    = 1,
    CD_STATE_DECEL_MON = 2,
    CD_STATE_ACTIVE    = 3,
    CD_STATE_FAULT     = 4,
} cd_state_t;

typedef enum {
    CD_FAULT_NONE         = 0,
    CD_FAULT_WATCHDOG     = 1,
    CD_FAULT_ANOMALY      = 2,
    CD_FAULT_SHARED_ABORT = 3,
} cd_fault_t;

/* Forward decl; we store a pointer to the wheel for speed_filtered
 * access and for wheel_apply_test_pwm() routing. */
struct wheel;
typedef struct wheel wheel_t;

typedef struct cd_motor {
    wheel_t *wheel;
    cd_state_t state;
    cd_fault_t last_fault;
    int8_t    entry_direction;   /* +1 or -1; undefined when !ACTIVE */
    float     entry_speed_cps;   /* fabsf(speed_filtered) at entry */
    uint32_t  entry_ms;          /* now_ms() at CD_ACTIVE entry */
    uint8_t   debounce_ticks;    /* in DECEL_MON */
    uint8_t   stop_ticks;        /* in CD_ACTIVE, below-threshold count */
    int16_t   current_pwm;       /* last CD-applied PWM (0 unless ACTIVE) */
    int32_t   watchdog_alarm_id; /* alarm_id returned by SDK; -1 when disarmed */
} cd_motor_t;

/* --- Public API ------------------------------------------------------ */

void counter_drive_init(cd_motor_t *cdm, wheel_t *w);

/* Called once per control tick, per motor.
 *
 * Order-of-call guarantee within a tick: call wheel_tick() FIRST for both
 * wheels (updates speed_filtered, drives WMODE_SPEED PWM), then call
 * counter_drive_tick() for both. CD can legitimately override PWM only
 * when wheel is in WMODE_IDLE. */
void counter_drive_tick(cd_motor_t *cdm);

/* Clears CD_FAULT state back to IDLE. Called from the NAVBOT_CMD_RESET
 * handler after safety_reset() succeeds; also callable directly. Does
 * NOT unlatch the shared_abort flag unless both motors are reset. */
void counter_drive_reset(cd_motor_t *cdm);

/* Helpers for the telemetry formatter. */
uint8_t  cd_state_wire(cd_state_t s);
uint8_t  cd_fault_wire(cd_fault_t f);
uint32_t cd_duration_ms(const cd_motor_t *cdm);

#endif
