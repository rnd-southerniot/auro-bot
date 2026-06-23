#include "pid.h"

void pid_init(pid_ctrl_t *p, float kp, float ki, float kd, float out_min, float out_max, float integral_max) {
    p->kp = kp;
    p->ki = ki;
    p->kd = kd;
    p->out_min = out_min;
    p->out_max = out_max;
    p->integral_max = integral_max;
    p->integral = 0.0f;
    p->prev_error = 0.0f;
    p->output = 0.0f;
    p->last_p_term = 0.0f;
    p->last_i_term = 0.0f;
    p->last_d_term = 0.0f;
}

float pid_update(pid_ctrl_t *p, float setpoint, float measurement, float dt) {
    float error = setpoint - measurement;
    float p_term = p->kp * error;
    float d_term = 0.0f;

    p->integral += error * dt;
    if (p->integral > p->integral_max) {
        p->integral = p->integral_max;
    }
    if (p->integral < -p->integral_max) {
        p->integral = -p->integral_max;
    }

    float i_term = p->ki * p->integral;

    if (dt > 0.0f) {
        d_term = p->kd * (error - p->prev_error) / dt;
    }

    p->prev_error = error;
    p->last_p_term = p_term;
    p->last_i_term = i_term;
    p->last_d_term = d_term;
    p->output = p_term + i_term + d_term;

    if (p->output > p->out_max) {
        p->output = p->out_max;
    }
    if (p->output < p->out_min) {
        p->output = p->out_min;
    }

    return p->output;
}

void pid_reset(pid_ctrl_t *p) {
    p->integral = 0.0f;
    p->prev_error = 0.0f;
    p->output = 0.0f;
    p->last_p_term = 0.0f;
    p->last_i_term = 0.0f;
    p->last_d_term = 0.0f;
}
