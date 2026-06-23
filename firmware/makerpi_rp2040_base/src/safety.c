#include "safety.h"

#include "hardware/gpio.h"
#include "hardware/pwm.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"

#include "config.h"
#include "pins.h"

static volatile safety_fault_t fault;
static bool motor_running;
static uint32_t motor_start_ms;

static void coast_all_motors(void) {
    uint slice_left = pwm_gpio_to_slice_num(PIN_LEFT_FWD);
    uint slice_right = pwm_gpio_to_slice_num(PIN_RIGHT_FWD);

    pwm_set_chan_level(slice_left, PWM_CHAN_A, 0);
    pwm_set_chan_level(slice_left, PWM_CHAN_B, 0);
    pwm_set_chan_level(slice_right, PWM_CHAN_A, 0);
    pwm_set_chan_level(slice_right, PWM_CHAN_B, 0);
}

static void estop_isr(uint gpio, uint32_t events) {
    (void)gpio;
    (void)events;
    __atomic_store_n(&fault, SAFETY_ESTOP, __ATOMIC_SEQ_CST);
    coast_all_motors();
}

void safety_init(void) {
    __atomic_store_n(&fault, SAFETY_OK, __ATOMIC_SEQ_CST);
    motor_running = false;
    motor_start_ms = 0;

    gpio_init(PIN_ESTOP);
    gpio_set_dir(PIN_ESTOP, GPIO_IN);
    gpio_pull_up(PIN_ESTOP);
    gpio_set_irq_enabled_with_callback(PIN_ESTOP, GPIO_IRQ_EDGE_FALL, true, estop_isr);

    sleep_ms(ESTOP_DEBOUNCE_MS);
    if (!gpio_get(PIN_ESTOP)) {
        __atomic_store_n(&fault, SAFETY_ESTOP, __ATOMIC_SEQ_CST);
    }
}

bool safety_is_faulted(void) {
    return __atomic_load_n(&fault, __ATOMIC_SEQ_CST) != SAFETY_OK;
}

safety_fault_t safety_get_fault(void) {
    return __atomic_load_n(&fault, __ATOMIC_SEQ_CST);
}

const char *safety_fault_name(safety_fault_t fault_code) {
    switch (fault_code) {
        case SAFETY_OK:          return "OK";
        case SAFETY_ESTOP:       return "ESTOP";
        case SAFETY_STALL:       return "STALL";
        case SAFETY_RUN_TIMEOUT: return "RUN_TIMEOUT";
        default:                 return "UNKNOWN";
    }
}

void safety_set_fault(safety_fault_t fault_code) {
    __atomic_store_n(&fault, fault_code, __ATOMIC_SEQ_CST);
    motor_running = false;
    coast_all_motors();
}

bool safety_reset(void) {
    uint32_t irq_state = save_and_disable_interrupts();
    if (!gpio_get(PIN_ESTOP)) {
        restore_interrupts(irq_state);
        return false;
    }
    fault = SAFETY_OK;
    motor_running = false;
    motor_start_ms = 0;
    restore_interrupts(irq_state);
    return true;
}

void safety_tick(uint32_t now_ms, bool motors_active) {
    safety_fault_t current = __atomic_load_n(&fault, __ATOMIC_SEQ_CST);
    if (current != SAFETY_OK) {
        motor_running = false;
        coast_all_motors();
        return;
    }

    if (motors_active) {
        if (!motor_running) {
            motor_start_ms = now_ms;
            motor_running = true;
        } else if (MAX_RUN_TIME_MS > 0 && (now_ms - motor_start_ms) >= MAX_RUN_TIME_MS) {
            safety_set_fault(SAFETY_RUN_TIMEOUT);
        }
    } else {
        motor_running = false;
    }
}
