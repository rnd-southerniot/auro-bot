#ifndef PID_H
#define PID_H

typedef struct {
    float kp;
    float ki;
    float kd;
    float out_min;
    float out_max;
    float integral_max;
    float integral;
    float prev_error;
    float output;
    float last_p_term;
    float last_i_term;
    float last_d_term;
} pid_ctrl_t;

void pid_init(pid_ctrl_t *p, float kp, float ki, float kd, float out_min, float out_max, float integral_max);
float pid_update(pid_ctrl_t *p, float setpoint, float measurement, float dt);
void pid_reset(pid_ctrl_t *p);

#endif
