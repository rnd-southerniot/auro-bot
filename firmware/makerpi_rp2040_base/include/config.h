#ifndef CONFIG_H
#define CONFIG_H

/*
 * Milestone 1 defaults.
 *
 * This firmware fixes the left/right ambiguity from the baseline repo:
 *   left wheel  = M2 / GP10-GP11 / encoder GP2-GP3
 *   right wheel = M1 / GP8-GP9  / encoder GP4-GP5
 */

#define LEFT_CPR_DEFAULT   3943
#define RIGHT_CPR_DEFAULT  3946

#define LEFT_WHEEL_RADIUS_M   0.0325f
#define RIGHT_WHEEL_RADIUS_M  0.0325f
#define WHEEL_SEPARATION_M    0.180f

#define MAX_LINEAR_MPS        0.25f
#define MAX_ANGULAR_RPS       2.50f
#define MAX_WHEEL_MPS         0.30f

#define CONTROL_LOOP_HZ         100
#define CONTROL_LOOP_PERIOD_US  10000
#define TELEMETRY_INTERVAL_MS   100

#define SPEED_FILTER_ALPHA      0.2f
#define SPEED_KP_DEFAULT        0.45f
#define SPEED_KI_DEFAULT        1.1f
#define SPEED_KD_DEFAULT        0.0f
#define SPEED_OUTPUT_MIN       -700.0f
#define SPEED_OUTPUT_MAX        700.0f
#define PID_INTEGRAL_MAX        5000.0f

#define ESTOP_DEBOUNCE_MS       50
#define COMMAND_TIMEOUT_MS      500
#define STALL_DUTY_THRESHOLD    200
#define STALL_DELTA_THRESHOLD   1
#define STALL_TIMEOUT_MS        800
#define STOP_SETPOINT_CPS_DEADBAND 20.0f
/*
 * Ignore stall accumulation briefly after a meaningful wheel setpoint change.
 *
 * This avoids false stall trips during ground startup, reversals, and other
 * low-speed transitions where duty rises before encoder motion fully settles.
 */
#define STALL_STARTUP_GRACE_MS  1200
#define STALL_SETPOINT_CHANGE_CPS 100.0f
/*
 * Optional continuous-run guard.
 *
 * Set to 0 to disable the fault for normal ROS/mobile operation.
 * Set to a positive value to latch SAFETY_RUN_TIMEOUT after that many
 * milliseconds of uninterrupted active wheel motion.
 */
#define MAX_RUN_TIME_MS         0

#define MOTOR_PWM_FREQ_HZ       16000
#define MOTOR_PWM_WRAP          999
#define MOTOR_MAX_DUTY          999
#define MOTOR_DUTY_SLEW_PER_TICK 30

/*
 * ADC voltage monitoring.
 *
 * Two external voltage dividers (ratio 1.691) scale the motor and LiDAR
 * power rails down to the RP2040 ADC range (0–3.3 V).
 *
 * real_voltage = (adc_raw / 4095.0) * ADC_VREF * VDIV_RATIO
 *
 * Readings are smoothed with a 4-sample moving average to reduce flicker.
 */
#define ADC_VREF                3.3f
#define VDIV_RATIO              1.691f
#define VBAT_INTERVAL_MS        500
#define VBAT_SMOOTH_SAMPLES     4

#endif
