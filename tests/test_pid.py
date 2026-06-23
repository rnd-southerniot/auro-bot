"""Unit tests for the PID controller.

Python oracle mirroring firmware pid.c logic. Validates integral windup
clamping, output saturation, derivative behavior, and reset.
"""

import pytest


class PidController:
    """Python oracle matching firmware pid_update / pid_init / pid_reset."""

    def __init__(
        self,
        kp: float,
        ki: float,
        kd: float,
        out_min: float,
        out_max: float,
        integral_max: float,
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.out_min = out_min
        self.out_max = out_max
        self.integral_max = integral_max
        self.integral = 0.0
        self.prev_error = 0.0
        self.output = 0.0
        self.last_p_term = 0.0
        self.last_i_term = 0.0
        self.last_d_term = 0.0

    def update(self, setpoint: float, measurement: float, dt: float) -> float:
        error = setpoint - measurement
        p_term = self.kp * error

        self.integral += error * dt
        if self.integral > self.integral_max:
            self.integral = self.integral_max
        if self.integral < -self.integral_max:
            self.integral = -self.integral_max

        i_term = self.ki * self.integral

        d_term = 0.0
        if dt > 0.0:
            d_term = self.kd * (error - self.prev_error) / dt

        self.prev_error = error
        self.last_p_term = p_term
        self.last_i_term = i_term
        self.last_d_term = d_term
        self.output = p_term + i_term + d_term

        if self.output > self.out_max:
            self.output = self.out_max
        if self.output < self.out_min:
            self.output = self.out_min

        return self.output

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
        self.output = 0.0
        self.last_p_term = 0.0
        self.last_i_term = 0.0
        self.last_d_term = 0.0


# Firmware defaults from config.h
KP = 0.45
KI = 1.1
KD = 0.0
OUT_MIN = -700.0
OUT_MAX = 700.0
INTEGRAL_MAX = 5000.0


def _make_pid(**kwargs) -> PidController:
    defaults = dict(
        kp=KP, ki=KI, kd=KD,
        out_min=OUT_MIN, out_max=OUT_MAX,
        integral_max=INTEGRAL_MAX,
    )
    defaults.update(kwargs)
    return PidController(**defaults)


class TestBasicBehavior:
    def test_zero_error_produces_zero_output(self):
        pid = _make_pid()
        output = pid.update(setpoint=100.0, measurement=100.0, dt=0.01)
        assert output == 0.0

    def test_positive_error_produces_positive_output(self):
        pid = _make_pid()
        output = pid.update(setpoint=100.0, measurement=0.0, dt=0.01)
        assert output > 0.0

    def test_negative_error_produces_negative_output(self):
        pid = _make_pid()
        output = pid.update(setpoint=-100.0, measurement=0.0, dt=0.01)
        assert output < 0.0

    def test_proportional_scales_with_error(self):
        pid = _make_pid(ki=0.0, kd=0.0)
        out1 = pid.update(setpoint=50.0, measurement=0.0, dt=0.01)
        pid.reset()
        out2 = pid.update(setpoint=100.0, measurement=0.0, dt=0.01)
        assert abs(out2 / out1 - 2.0) < 0.01


class TestOutputClamping:
    def test_output_clamped_to_max(self):
        pid = _make_pid()
        output = pid.update(setpoint=10000.0, measurement=0.0, dt=0.01)
        assert output == OUT_MAX

    def test_output_clamped_to_min(self):
        pid = _make_pid()
        output = pid.update(setpoint=-10000.0, measurement=0.0, dt=0.01)
        assert output == OUT_MIN


class TestIntegralWindup:
    def test_integral_clamped_to_max(self):
        pid = _make_pid(kp=0.0, kd=0.0)
        # Accumulate a massive integral.
        for _ in range(100000):
            pid.update(setpoint=1000.0, measurement=0.0, dt=1.0)
        assert pid.integral == INTEGRAL_MAX

    def test_integral_clamped_to_negative_max(self):
        pid = _make_pid(kp=0.0, kd=0.0)
        for _ in range(100000):
            pid.update(setpoint=-1000.0, measurement=0.0, dt=1.0)
        assert pid.integral == -INTEGRAL_MAX

    def test_integral_accumulates_correctly(self):
        pid = _make_pid(kp=0.0, ki=1.0, kd=0.0)
        # error=10.0, dt=0.1 => integral += 1.0 each step
        for _ in range(5):
            pid.update(setpoint=10.0, measurement=0.0, dt=0.1)
        assert abs(pid.integral - 5.0) < 1e-6


class TestDerivative:
    def test_derivative_zero_when_kd_zero(self):
        pid = _make_pid(kp=0.0, ki=0.0, kd=0.0)
        # First update seeds prev_error.
        pid.update(setpoint=0.0, measurement=0.0, dt=0.01)
        # Step change in setpoint — with kd=0, output should be 0.
        output = pid.update(setpoint=100.0, measurement=0.0, dt=0.01)
        assert output == 0.0

    def test_derivative_responds_to_error_change(self):
        pid = _make_pid(kp=0.0, ki=0.0, kd=1.0)
        pid.update(setpoint=0.0, measurement=0.0, dt=0.01)
        # Step from error=0 to error=100, d_term = 1.0 * 100 / 0.01 = 10000
        # But output clamped to OUT_MAX=700.
        output = pid.update(setpoint=100.0, measurement=0.0, dt=0.01)
        assert output == OUT_MAX


class TestDtEdgeCases:
    def test_dt_zero_skips_derivative(self):
        pid = _make_pid(kp=1.0, ki=0.0, kd=1.0)
        # dt=0 should not divide by zero.
        output = pid.update(setpoint=10.0, measurement=0.0, dt=0.0)
        # Only P term: 1.0 * 10.0 = 10.0. D term skipped.
        assert abs(output - 10.0) < 1e-6

    def test_very_small_dt(self):
        pid = _make_pid(kp=0.0, ki=0.0, kd=0.001)
        pid.update(setpoint=0.0, measurement=0.0, dt=1e-6)
        output = pid.update(setpoint=1.0, measurement=0.0, dt=1e-6)
        # Should clamp, not produce infinity.
        assert output == OUT_MAX


class TestReset:
    def test_reset_clears_state(self):
        pid = _make_pid()
        pid.update(setpoint=100.0, measurement=0.0, dt=0.01)
        assert pid.integral != 0.0
        assert pid.prev_error != 0.0

        pid.reset()
        assert pid.integral == 0.0
        assert pid.prev_error == 0.0
        assert pid.output == 0.0

    def test_output_after_reset_matches_fresh(self):
        pid1 = _make_pid()
        pid2 = _make_pid()

        # Drive pid1 for a while, then reset.
        for _ in range(50):
            pid1.update(setpoint=200.0, measurement=50.0, dt=0.01)
        pid1.reset()

        out1 = pid1.update(setpoint=100.0, measurement=0.0, dt=0.01)
        out2 = pid2.update(setpoint=100.0, measurement=0.0, dt=0.01)
        assert abs(out1 - out2) < 1e-6


class TestDiagnosticFields:
    def test_p_term_tracked(self):
        pid = _make_pid(ki=0.0, kd=0.0)
        pid.update(setpoint=100.0, measurement=0.0, dt=0.01)
        assert abs(pid.last_p_term - (KP * 100.0)) < 1e-6

    def test_i_term_tracked(self):
        pid = _make_pid(kp=0.0, kd=0.0)
        pid.update(setpoint=10.0, measurement=0.0, dt=0.1)
        # integral = 10.0 * 0.1 = 1.0, i_term = KI * 1.0
        assert abs(pid.last_i_term - (KI * 1.0)) < 1e-6

    def test_d_term_tracked(self):
        pid = _make_pid(kp=0.0, ki=0.0, kd=1.0)
        pid.update(setpoint=0.0, measurement=0.0, dt=0.01)
        pid.update(setpoint=50.0, measurement=0.0, dt=0.01)
        # d_term = 1.0 * (50 - 0) / 0.01 = 5000, clamped to OUT_MAX
        assert pid.last_d_term > 0.0

    def test_reset_clears_diagnostic_fields(self):
        pid = _make_pid()
        pid.update(setpoint=100.0, measurement=0.0, dt=0.01)
        assert pid.last_p_term != 0.0
        pid.reset()
        assert pid.last_p_term == 0.0
        assert pid.last_i_term == 0.0
        assert pid.last_d_term == 0.0
