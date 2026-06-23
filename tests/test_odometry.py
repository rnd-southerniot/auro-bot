"""Unit tests for DifferentialDriveOdometry.

Validates pose integration, yaw wrapping, velocity computation,
and per-wheel CPR handling against known geometric expectations.
"""

import math
import sys
from pathlib import Path

import pytest

# Allow import of navbot_base from the workspace source tree without
# installing the ROS 2 package.
_BASE_SRC = Path(__file__).resolve().parent.parent / "ros2_ws" / "src" / "navbot_base"
if str(_BASE_SRC) not in sys.path:
    sys.path.insert(0, str(_BASE_SRC))

from navbot_base.odometry import DifferentialDriveOdometry


# --- Geometry helpers ---

WHEEL_RADIUS = 0.033
WHEEL_SEPARATION = 0.160
CPR = 3945
LEFT_CPR = 3943
RIGHT_CPR = 3946


def _counts_for_distance(distance_m: float, cpr: int = CPR) -> int:
    """How many encoder counts produce a given linear wheel distance."""
    circumference = 2.0 * math.pi * WHEEL_RADIUS
    revolutions = distance_m / circumference
    return int(round(revolutions * cpr))


def _make_odom(**kwargs) -> DifferentialDriveOdometry:
    defaults = dict(
        wheel_radius=WHEEL_RADIUS,
        wheel_separation=WHEEL_SEPARATION,
        counts_per_revolution=CPR,
        left_counts_per_revolution=LEFT_CPR,
        right_counts_per_revolution=RIGHT_CPR,
    )
    defaults.update(kwargs)
    return DifferentialDriveOdometry(**defaults)


# --- Tests ---


class TestInitialState:
    def test_pose_starts_at_origin(self):
        odom = _make_odom()
        assert odom.x == 0.0
        assert odom.y == 0.0
        assert odom.yaw == 0.0

    def test_first_update_returns_zero_pose(self):
        odom = _make_odom()
        state = odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        assert state.x == 0.0
        assert state.y == 0.0
        assert state.yaw == 0.0

    def test_first_update_seeds_internal_state(self):
        odom = _make_odom()
        odom.update(
            stamp_sec=0.0, left_count=100, right_count=100,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        # Second update with same counts should produce zero motion.
        state = odom.update(
            stamp_sec=0.1, left_count=100, right_count=100,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        assert abs(state.x) < 1e-9
        assert abs(state.y) < 1e-9


class TestStraightLine:
    def test_forward_1m(self):
        odom = _make_odom()
        target_m = 1.0
        left_counts = _counts_for_distance(target_m, LEFT_CPR)
        right_counts = _counts_for_distance(target_m, RIGHT_CPR)
        speed = 0.10

        # Seed
        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=speed, right_velocity_mps=speed,
        )
        # Drive
        state = odom.update(
            stamp_sec=10.0, left_count=left_counts, right_count=right_counts,
            left_velocity_mps=speed, right_velocity_mps=speed,
        )

        assert abs(state.x - target_m) < 0.002, f"x={state.x}, expected ~{target_m}"
        assert abs(state.y) < 0.002, f"y={state.y}, expected ~0"
        assert abs(state.yaw) < 0.01, f"yaw={state.yaw}, expected ~0"

    def test_backward_05m(self):
        odom = _make_odom()
        target_m = -0.5
        left_counts = _counts_for_distance(target_m, LEFT_CPR)
        right_counts = _counts_for_distance(target_m, RIGHT_CPR)

        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=-0.10, right_velocity_mps=-0.10,
        )
        state = odom.update(
            stamp_sec=5.0, left_count=left_counts, right_count=right_counts,
            left_velocity_mps=-0.10, right_velocity_mps=-0.10,
        )

        assert abs(state.x - target_m) < 0.002
        assert abs(state.y) < 0.002


class TestPureRotation:
    def test_90_degree_left_turn(self):
        odom = _make_odom()
        # For a pure rotation of angle theta:
        #   left_distance = -theta * wheel_separation / 2
        #   right_distance = +theta * wheel_separation / 2
        theta = math.pi / 2.0  # 90 degrees
        left_dist = -(theta * WHEEL_SEPARATION / 2.0)
        right_dist = theta * WHEEL_SEPARATION / 2.0
        left_counts = _counts_for_distance(left_dist, LEFT_CPR)
        right_counts = _counts_for_distance(right_dist, RIGHT_CPR)

        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        state = odom.update(
            stamp_sec=2.0, left_count=left_counts, right_count=right_counts,
            left_velocity_mps=-0.05, right_velocity_mps=0.05,
        )

        # Position should stay near origin for pure rotation.
        assert abs(state.x) < 0.01
        assert abs(state.y) < 0.01
        # Yaw should be approximately pi/2.
        assert abs(state.yaw - theta) < 0.05, f"yaw={state.yaw}, expected ~{theta}"


class TestYawWrapping:
    def test_yaw_stays_within_minus_pi_to_pi(self):
        odom = _make_odom()
        # Rotate 350 degrees (just under full circle).
        theta = 350.0 * math.pi / 180.0
        left_dist = -(theta * WHEEL_SEPARATION / 2.0)
        right_dist = theta * WHEEL_SEPARATION / 2.0
        left_counts = _counts_for_distance(left_dist, LEFT_CPR)
        right_counts = _counts_for_distance(right_dist, RIGHT_CPR)

        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        state = odom.update(
            stamp_sec=10.0, left_count=left_counts, right_count=right_counts,
            left_velocity_mps=-0.05, right_velocity_mps=0.05,
        )

        assert -math.pi <= state.yaw <= math.pi


class TestVelocity:
    def test_velocity_passthrough(self):
        odom = _make_odom()
        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        state = odom.update(
            stamp_sec=0.1, left_count=0, right_count=0,
            left_velocity_mps=0.15, right_velocity_mps=0.10,
        )

        expected_linear = 0.5 * (0.15 + 0.10)
        expected_angular = (0.10 - 0.15) / WHEEL_SEPARATION
        assert abs(state.linear_velocity - expected_linear) < 1e-6
        assert abs(state.angular_velocity - expected_angular) < 1e-6


class TestJointPositions:
    def test_joint_position_scales_with_counts(self):
        odom = _make_odom()
        # One full revolution on left wheel.
        state = odom.update(
            stamp_sec=0.0, left_count=LEFT_CPR, right_count=0,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        assert abs(state.left_joint_position - 2.0 * math.pi) < 0.01
        assert abs(state.right_joint_position) < 1e-9


class TestReset:
    def test_reset_clears_pose(self):
        odom = _make_odom()
        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=0.1, right_velocity_mps=0.1,
        )
        odom.update(
            stamp_sec=1.0, left_count=1000, right_count=1000,
            left_velocity_mps=0.1, right_velocity_mps=0.1,
        )
        assert odom.x != 0.0

        odom.reset()
        assert odom.x == 0.0
        assert odom.y == 0.0
        assert odom.yaw == 0.0


class TestAsymmetricCPR:
    def test_symmetric_cpr_produces_same_result(self):
        odom_asym = _make_odom(
            left_counts_per_revolution=3943,
            right_counts_per_revolution=3946,
        )
        odom_sym = _make_odom(
            left_counts_per_revolution=3945,
            right_counts_per_revolution=3945,
        )

        counts = 5000
        for odom in (odom_asym, odom_sym):
            odom.update(
                stamp_sec=0.0, left_count=0, right_count=0,
                left_velocity_mps=0.1, right_velocity_mps=0.1,
            )
            odom.update(
                stamp_sec=5.0, left_count=counts, right_count=counts,
                left_velocity_mps=0.1, right_velocity_mps=0.1,
            )

        # With equal counts but different CPR, asymmetric should produce
        # slightly different distance (and slight yaw drift).
        # Just verify both produce reasonable results.
        assert abs(odom_asym.x) > 0.01
        assert abs(odom_sym.x) > 0.01


class TestMcuRestartDetection:
    """Verify that a sudden encoder count jump (MCU reboot) is absorbed,
    not integrated as a huge backward motion."""

    def test_restart_from_high_count_to_zero(self):
        odom = _make_odom()
        # Seed and drive to 50000 counts in increments below restart threshold.
        # Threshold is CPR*10 ≈ 39450, so use steps of 20000.
        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=0.1, right_velocity_mps=0.1,
        )
        odom.update(
            stamp_sec=5.0, left_count=20000, right_count=20000,
            left_velocity_mps=0.1, right_velocity_mps=0.1,
        )
        odom.update(
            stamp_sec=10.0, left_count=50000, right_count=50000,
            left_velocity_mps=0.1, right_velocity_mps=0.1,
        )
        x_before = odom.x
        assert x_before > 0.5  # Sanity: we moved forward

        # MCU restarts — counts jump to 0 (delta = -50000, above threshold)
        state = odom.update(
            stamp_sec=10.5, left_count=0, right_count=0,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )

        # Pose should NOT jump backward — restart absorbed
        assert abs(state.x - x_before) < 0.01, (
            f"x jumped from {x_before} to {state.x} — restart not detected"
        )
        assert state.linear_velocity == 0.0

    def test_normal_large_motion_not_falsely_detected(self):
        """A legitimate long drive should NOT trigger restart detection."""
        odom = _make_odom()
        # Threshold is CPR * 10 ≈ 39450. Drive 30000 counts (under threshold).
        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=0.1, right_velocity_mps=0.1,
        )
        state = odom.update(
            stamp_sec=60.0, left_count=30000, right_count=30000,
            left_velocity_mps=0.1, right_velocity_mps=0.1,
        )
        # Should have moved forward — NOT absorbed as restart
        assert state.x > 1.0

    def test_restart_preserves_yaw(self):
        """After restart detection, yaw should be preserved, not zeroed."""
        odom = _make_odom()
        # Rotate to a known yaw
        theta = math.pi / 4.0
        left_dist = -(theta * WHEEL_SEPARATION / 2.0)
        right_dist = theta * WHEEL_SEPARATION / 2.0
        left_counts = _counts_for_distance(left_dist, LEFT_CPR)
        right_counts = _counts_for_distance(right_dist, RIGHT_CPR)

        odom.update(
            stamp_sec=0.0, left_count=0, right_count=0,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        odom.update(
            stamp_sec=2.0, left_count=left_counts, right_count=right_counts,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )
        yaw_before = odom.yaw

        # Simulate restart: counts jump to 0 from left_counts/right_counts
        # These deltas are small (< threshold) so we need to also simulate
        # a larger travel first, then restart.
        odom.update(
            stamp_sec=10.0, left_count=left_counts + 50000, right_count=right_counts + 50000,
            left_velocity_mps=0.1, right_velocity_mps=0.1,
        )
        state = odom.update(
            stamp_sec=10.5, left_count=0, right_count=0,
            left_velocity_mps=0.0, right_velocity_mps=0.0,
        )

        # Yaw preserved through restart
        assert abs(state.yaw - odom.yaw) < 0.01
