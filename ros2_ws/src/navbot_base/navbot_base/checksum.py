"""Navbot serial protocol XOR checksum utilities.

Standalone module with no ROS dependencies so it can be used in
both the serial bridge node and off-target unit tests.
"""


def compute_checksum(data: str) -> str:
    """Compute XOR checksum of a string, return as 2-char uppercase hex."""
    csum = 0
    for ch in data:
        csum ^= ord(ch)
    return f"{csum:02X}"


def append_checksum(line: str) -> str:
    """Append *XX checksum suffix to a command line."""
    stripped = line.strip()
    return f"{stripped}*{compute_checksum(stripped)}"


def validate_and_strip_checksum(line: str) -> tuple[str, bool]:
    """Validate and strip *XX checksum suffix.

    Returns (payload, valid). If no '*' is present, returns (line, True)
    for backward compatibility. If '*' is present but checksum is wrong,
    returns (line, False).
    """
    star_idx = line.rfind("*")
    if star_idx < 0:
        return line, True

    payload = line[:star_idx]
    suffix = line[star_idx + 1:]
    if len(suffix) != 2:
        return line, False

    try:
        received = int(suffix, 16)
    except ValueError:
        return line, False

    expected = int(compute_checksum(payload), 16)
    if received != expected:
        return line, False

    return payload, True
