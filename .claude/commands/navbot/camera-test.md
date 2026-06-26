---
description: Camera test — check the XIAO ESP32-S3 Sense Wi-Fi camera is live (status + a snapshot)
allowed-tools: Bash(curl:*), Bash(python3:*)
---

Verify the robot's **eyes** — the XIAO ESP32-S3 Sense Wi-Fi camera (P6) — without
ROS. The camera serves JPEG over HTTP and is reachable on Wi-Fi (default
`http://192.168.68.107`, DHCP-reserved; override with `$NAVBOT_CAMERA_URL`).

```bash
CAM="${NAVBOT_CAMERA_URL:-http://192.168.68.107}"
echo "camera: $CAM"
# 1) Liveness/health JSON (fps, motion, rssi, uptime, version):
curl -s --max-time 6 "$CAM/status" | python3 -m json.tool 2>/dev/null \
  || { echo "NO /status — camera unreachable (powered? on AP 'Auro_IoT'?)"; exit 1; }
# 2) Grab one snapshot and confirm it's a valid JPEG:
OUT="/tmp/navbot_camtest.jpg"
curl -s --max-time 8 "$CAM/snapshot" -o "$OUT"
SZ=$(wc -c < "$OUT")
SOI=$(head -c3 "$OUT" | od -An -tx1 | tr -d ' ')
echo "snapshot: $OUT ($SZ bytes, SOI=$SOI)"
[ "$SOI" = "ffd8ff" ] && echo "PASS — valid JPEG" || echo "FAIL — not a JPEG"
```

PASS = `/status` returns JSON **and** the snapshot starts with `ffd8ff` (JFIF
SOI). The brain's `look()` uses this exact `/snapshot`. If unreachable: confirm
the XIAO is powered, joined AP "Auro_IoT," and still at the reserved address
(`ip neigh show 192.168.68.107` should show MAC `8c:bf:ea:8e:65:04`).
