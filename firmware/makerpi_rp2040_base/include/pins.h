#ifndef PINS_H
#define PINS_H

#include <stdbool.h>

/*
 * Explicit robot mapping used by the navbot firmware.
 *
 * Left wheel:
 *   M2 -> GP10 / GP11
 *   encoder -> GP2 / GP3
 *
 * Right wheel:
 *   M1 -> GP8 / GP9
 *   encoder -> GP4 / GP5
 *   swap_dir enabled so positive command == robot forward
 */

#define PIN_LEFT_FWD     10
#define PIN_LEFT_REV     11
#define PIN_LEFT_ENC_A   2
#define PIN_LEFT_ENC_B   3

#define PIN_RIGHT_FWD    8
#define PIN_RIGHT_REV    9
#define PIN_RIGHT_ENC_A  4
#define PIN_RIGHT_ENC_B  5

#define PIN_ESTOP        20

#define PIN_ADC_MOTOR_V  27
#define PIN_ADC_LIDAR_V  28

#define PIN_BUZZER       22

#define LEFT_WHEEL_SWAP_DIR   false
#define RIGHT_WHEEL_SWAP_DIR  true

#endif
