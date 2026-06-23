"""Unit tests for the navbot serial protocol parser.

These tests mirror the firmware serial_parser.c logic in Python to validate
protocol parsing rules without requiring the RP2040 hardware. The Python
implementation here is a test oracle — it does NOT replace the C parser.

If these tests pass but the firmware behaves differently, the C parser
has a bug (or this oracle diverged from the spec).
"""

import math
import sys
from pathlib import Path

import pytest

_BASE_SRC = Path(__file__).resolve().parent.parent / "ros2_ws" / "src" / "navbot_base"
if str(_BASE_SRC) not in sys.path:
    sys.path.insert(0, str(_BASE_SRC))

from navbot_base.checksum import (
    append_checksum,
    compute_checksum,
    validate_and_strip_checksum,
)


# --- Python oracle for firmware parser ---

NAVBOT_PROTOCOL_MAX_LINE = 128


class ParseResult:
    OK = "OK"
    EMPTY = "EMPTY"
    UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
    BAD_ARGUMENTS = "BAD_ARGUMENTS"
    BAD_CHECKSUM = "BAD_CHECKSUM"


class Command:
    def __init__(self, cmd_type: str, value_1: float = 0.0, value_2: float = 0.0):
        self.type = cmd_type
        self.value_1 = value_1
        self.value_2 = value_2


def parse_command_line(line: str) -> tuple[str, Command | None]:
    """Python oracle matching firmware navbot_parse_command_line behavior."""
    if line is None:
        return ParseResult.BAD_ARGUMENTS, None

    # Strip and validate checksum before any other processing.
    payload, checksum_valid = validate_and_strip_checksum(line)
    if not checksum_valid:
        return ParseResult.BAD_CHECKSUM, None

    trimmed = payload.strip().upper()
    if not trimmed:
        return ParseResult.EMPTY, None

    if trimmed == "PING":
        return ParseResult.OK, Command("PING")
    if trimmed == "STOP":
        return ParseResult.OK, Command("STOP")
    if trimmed == "RESET":
        return ParseResult.OK, Command("RESET")
    if trimmed == "ESTOP":
        return ParseResult.OK, Command("ESTOP")

    for prefix, cmd_type in [("CMD_VEL", "CMD_VEL"), ("WHEEL_VEL", "WHEEL_VEL")]:
        if trimmed.startswith(prefix):
            rest = trimmed[len(prefix):]
            if not rest or not rest[0] == " ":
                return ParseResult.BAD_ARGUMENTS, None
            parts = rest.split()
            if len(parts) != 2:
                return ParseResult.BAD_ARGUMENTS, None
            try:
                v1 = float(parts[0])
                v2 = float(parts[1])
            except ValueError:
                return ParseResult.BAD_ARGUMENTS, None
            if not math.isfinite(v1) or not math.isfinite(v2):
                return ParseResult.BAD_ARGUMENTS, None
            return ParseResult.OK, Command(cmd_type, v1, v2)

    return ParseResult.UNKNOWN_COMMAND, None


# --- Tests ---


class TestSimpleCommands:
    @pytest.mark.parametrize("line,expected_type", [
        ("PING", "PING"),
        ("STOP", "STOP"),
        ("RESET", "RESET"),
        ("ESTOP", "ESTOP"),
    ])
    def test_bare_commands(self, line, expected_type):
        result, cmd = parse_command_line(line)
        assert result == ParseResult.OK
        assert cmd.type == expected_type

    @pytest.mark.parametrize("line", [
        "ping", "Ping", "pInG", "  PING  ", "  ping  ",
    ])
    def test_case_insensitive(self, line):
        result, cmd = parse_command_line(line)
        assert result == ParseResult.OK
        assert cmd.type == "PING"


class TestCmdVel:
    def test_valid_cmd_vel(self):
        result, cmd = parse_command_line("CMD_VEL 0.10 0.50")
        assert result == ParseResult.OK
        assert cmd.type == "CMD_VEL"
        assert abs(cmd.value_1 - 0.10) < 1e-6
        assert abs(cmd.value_2 - 0.50) < 1e-6

    def test_negative_values(self):
        result, cmd = parse_command_line("CMD_VEL -0.15 -1.20")
        assert result == ParseResult.OK
        assert abs(cmd.value_1 - (-0.15)) < 1e-6
        assert abs(cmd.value_2 - (-1.20)) < 1e-6

    def test_zero_values(self):
        result, cmd = parse_command_line("CMD_VEL 0.0 0.0")
        assert result == ParseResult.OK
        assert cmd.value_1 == 0.0
        assert cmd.value_2 == 0.0

    def test_missing_args(self):
        result, _ = parse_command_line("CMD_VEL")
        assert result == ParseResult.BAD_ARGUMENTS

    def test_one_arg_only(self):
        result, _ = parse_command_line("CMD_VEL 0.10")
        assert result == ParseResult.BAD_ARGUMENTS

    def test_three_args(self):
        result, _ = parse_command_line("CMD_VEL 0.10 0.50 0.30")
        assert result == ParseResult.BAD_ARGUMENTS

    def test_non_numeric(self):
        result, _ = parse_command_line("CMD_VEL abc def")
        assert result == ParseResult.BAD_ARGUMENTS

    def test_inf_rejected(self):
        result, _ = parse_command_line("CMD_VEL inf 0.0")
        assert result == ParseResult.BAD_ARGUMENTS

    def test_nan_rejected(self):
        result, _ = parse_command_line("CMD_VEL nan 0.0")
        assert result == ParseResult.BAD_ARGUMENTS


class TestWheelVel:
    def test_valid_wheel_vel(self):
        result, cmd = parse_command_line("WHEEL_VEL 0.05 0.08")
        assert result == ParseResult.OK
        assert cmd.type == "WHEEL_VEL"
        assert abs(cmd.value_1 - 0.05) < 1e-6
        assert abs(cmd.value_2 - 0.08) < 1e-6

    def test_missing_args(self):
        result, _ = parse_command_line("WHEEL_VEL")
        assert result == ParseResult.BAD_ARGUMENTS


class TestEdgeCases:
    def test_empty_string(self):
        result, _ = parse_command_line("")
        assert result == ParseResult.EMPTY

    def test_whitespace_only(self):
        result, _ = parse_command_line("   ")
        assert result == ParseResult.EMPTY

    def test_unknown_command(self):
        result, _ = parse_command_line("FLY 100")
        assert result == ParseResult.UNKNOWN_COMMAND

    def test_leading_trailing_whitespace(self):
        result, cmd = parse_command_line("  CMD_VEL 0.10 0.20  ")
        assert result == ParseResult.OK
        assert cmd.type == "CMD_VEL"


class TestChecksumIntegration:
    def test_valid_checksum_accepted(self):
        line = append_checksum("PING")
        result, cmd = parse_command_line(line)
        assert result == ParseResult.OK
        assert cmd.type == "PING"

    def test_wrong_checksum_rejected(self):
        result, _ = parse_command_line("PING*00")
        # PING XOR is not 00, so this should fail
        ping_csum = compute_checksum("PING")
        if ping_csum != "00":
            assert result == ParseResult.BAD_CHECKSUM

    def test_cmd_vel_with_checksum(self):
        line = append_checksum("CMD_VEL 0.15 0.80")
        result, cmd = parse_command_line(line)
        assert result == ParseResult.OK
        assert cmd.type == "CMD_VEL"
        assert abs(cmd.value_1 - 0.15) < 1e-6
        assert abs(cmd.value_2 - 0.80) < 1e-6

    def test_no_checksum_still_accepted(self):
        result, cmd = parse_command_line("STOP")
        assert result == ParseResult.OK
        assert cmd.type == "STOP"

    def test_truncated_checksum_rejected(self):
        result, _ = parse_command_line("PING*A")
        assert result == ParseResult.BAD_CHECKSUM

    def test_corrupt_payload_detected(self):
        csum = compute_checksum("PING")
        result, _ = parse_command_line(f"PONG*{csum}")
        assert result == ParseResult.BAD_CHECKSUM
