#ifndef NAVBOT_SAFETY_H
#define NAVBOT_SAFETY_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    SAFETY_OK = 0,
    SAFETY_ESTOP,
    SAFETY_STALL,
    SAFETY_RUN_TIMEOUT,
} safety_fault_t;

void safety_init(void);
bool safety_is_faulted(void);
safety_fault_t safety_get_fault(void);
const char *safety_fault_name(safety_fault_t fault);
void safety_set_fault(safety_fault_t fault);
bool safety_reset(void);
void safety_tick(uint32_t now_ms, bool motors_active);

#endif
