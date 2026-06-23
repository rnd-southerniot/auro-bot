"""Unit tests for the navbot serial protocol XOR checksum.

Validates the Python checksum implementation and the
validate_and_strip_checksum function for correct and corrupt data.
"""

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


class TestComputeChecksum:
    def test_empty_string(self):
        assert compute_checksum("") == "00"

    def test_single_char(self):
        assert compute_checksum("A") == f"{ord('A'):02X}"

    def test_known_xor(self):
        # "AB" => 0x41 ^ 0x42 = 0x03
        assert compute_checksum("AB") == "03"

    def test_ping(self):
        data = "PING"
        expected = 0
        for ch in data:
            expected ^= ord(ch)
        assert compute_checksum(data) == f"{expected:02X}"

    def test_odom_line(self):
        data = "ODOM 12345 1000 1001 0.0500 0.0510"
        csum = 0
        for ch in data:
            csum ^= ord(ch)
        assert compute_checksum(data) == f"{csum:02X}"


class TestAppendChecksum:
    def test_appends_star_and_hex(self):
        result = append_checksum("PING")
        assert result.startswith("PING*")
        assert len(result) == len("PING") + 3  # *XX

    def test_strips_whitespace_before_computing(self):
        result = append_checksum("  STOP  ")
        assert result.startswith("STOP*")

    def test_roundtrip(self):
        line = "CMD_VEL 0.1000 0.5000"
        with_checksum = append_checksum(line)
        payload, valid = validate_and_strip_checksum(with_checksum)
        assert valid
        assert payload == line


class TestValidateAndStripChecksum:
    def test_no_star_accepted(self):
        payload, valid = validate_and_strip_checksum("PING")
        assert valid
        assert payload == "PING"

    def test_valid_checksum_stripped(self):
        line = "STOP"
        csum = compute_checksum(line)
        payload, valid = validate_and_strip_checksum(f"{line}*{csum}")
        assert valid
        assert payload == "STOP"

    def test_wrong_checksum_rejected(self):
        payload, valid = validate_and_strip_checksum("PING*00")
        # 00 is almost certainly wrong for PING
        ping_csum = compute_checksum("PING")
        if ping_csum == "00":
            assert valid  # edge case: if PING XOR happens to be 00
        else:
            assert not valid

    def test_truncated_checksum_rejected(self):
        payload, valid = validate_and_strip_checksum("PING*A")
        assert not valid

    def test_non_hex_checksum_rejected(self):
        payload, valid = validate_and_strip_checksum("PING*ZZ")
        assert not valid

    def test_empty_after_star_rejected(self):
        payload, valid = validate_and_strip_checksum("PING*")
        assert not valid

    def test_odom_roundtrip(self):
        data = "ODOM 99999 50000 50001 0.1234 0.1235"
        with_csum = f"{data}*{compute_checksum(data)}"
        payload, valid = validate_and_strip_checksum(with_csum)
        assert valid
        assert payload == data

    def test_corruption_detected(self):
        data = "ODOM 99999 50000 50001 0.1234 0.1235"
        csum = compute_checksum(data)
        # Flip one character
        corrupted = "ODOM 99999 50001 50001 0.1234 0.1235"
        payload, valid = validate_and_strip_checksum(f"{corrupted}*{csum}")
        assert not valid


class TestChecksumAgreement:
    """Verify Python checksum matches the C firmware algorithm.

    The C algorithm is: XOR all bytes before '*', print as %02X uppercase.
    This test class verifies our Python implementation produces the same
    results for known test vectors.
    """

    @pytest.mark.parametrize("data,expected_hex", [
        ("", "00"),
        ("A", "41"),
        ("AB", "03"),
        ("PING", f"{ord('P') ^ ord('I') ^ ord('N') ^ ord('G'):02X}"),
        ("ACK STOP", f"{ord('A') ^ ord('C') ^ ord('K') ^ ord(' ') ^ ord('S') ^ ord('T') ^ ord('O') ^ ord('P'):02X}"),
    ])
    def test_known_vectors(self, data, expected_hex):
        assert compute_checksum(data) == expected_hex
