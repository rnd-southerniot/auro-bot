#!/usr/bin/env python3
import argparse
import time

import serial


def classify_line(text: str) -> str:
    if text.startswith("ACK "):
        return "[ACK ]"
    if text.startswith("ERR "):
        return "[ERR ]"
    if text.startswith("STATE "):
        return "[STATE]"
    if text.startswith("ODOM "):
        return "[ODOM]"
    return "[RAW ]"


def print_line(text: str) -> None:
    print(f"{classify_line(text)} {text}")


def read_for(ser: serial.Serial, seconds: float) -> None:
    end_time = time.monotonic() + seconds
    while time.monotonic() < end_time:
        line = ser.readline()
        if line:
            print_line(line.decode("utf-8", errors="replace").rstrip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple host-side serial check for navbot RP2040 firmware.")
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serial device path")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--send", action="append", default=[], help="Command to send; may be repeated")
    parser.add_argument("--read-seconds", type=float, default=1.0, help="Seconds to read after each command")
    parser.add_argument("--stream-seconds", type=float, default=0.0, help="Extra seconds to keep streaming after all commands")
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.2) as ser:
        print(f"opened {args.port} @ {args.baud}")
        time.sleep(0.2)
        read_for(ser, 0.5)

        if not args.send:
            idle_stream = args.stream_seconds if args.stream_seconds > 0.0 else 3.0
            print(f"no commands given; streaming for {idle_stream:.1f}s")
            read_for(ser, idle_stream)
            return

        for command in args.send:
            print(f">>> {command}")
            ser.write((command.strip() + "\n").encode("utf-8"))
            read_for(ser, args.read_seconds)

        if args.stream_seconds > 0.0:
            print(f"--- streaming for {args.stream_seconds:.1f}s ---")
            read_for(ser, args.stream_seconds)


if __name__ == "__main__":
    main()
