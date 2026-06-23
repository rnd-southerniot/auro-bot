# Flashing the RP2040 Firmware

## Prerequisites

- [Pico SDK](https://github.com/raspberrypi/pico-sdk) installed and `PICO_SDK_PATH` set
- ARM GCC toolchain (`arm-none-eabi-gcc`)
- CMake 3.13+

## Build

```bash
cd firmware/makerpi_rp2040_base
mkdir -p build && cd build
cmake .. -DPICO_SDK_PATH=$PICO_SDK_PATH
make -j$(nproc)
```

Output: `build/firmware.uf2`

## Flash

1. Disconnect the RP2040 USB cable
2. Hold the **BOOTSEL** button on the Maker Pi RP2040
3. While holding BOOTSEL, connect USB to the build machine (Pi or laptop)
4. Release BOOTSEL — the board mounts as a USB mass storage device (`RPI-RP2`)
5. Copy the firmware:

```bash
cp build/firmware.uf2 /media/$USER/RPI-RP2/
```

The board reboots automatically after the copy completes.

## Verify

```bash
python3 -m serial.tools.miniterm /dev/ttyACM0 115200
```

Type `PING` and press Enter. Expected response:

```
ACK PING
```

Type `STOP` to confirm motor control path:

```
ACK STOP
```

## Pre-flash Safety

Always archive the current known-good binary before flashing:

```bash
cp build/firmware.uf2 build/firmware_backup_$(date +%Y%m%d_%H%M%S).uf2
```

If the new firmware fails validation, re-flash the backup using the same BOOTSEL procedure.
