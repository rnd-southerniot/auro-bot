---
description: Voice-appliance status — are the autostart services (or manual voice loop) up on the robot?
allowed-tools: Bash(ssh navbot-pi:*)
---

Report whether the **voice appliance** is running on the robot, read-only. Checks
the P7 systemd units (if installed) and the live voice loop / web API. No motion.

1. Confirm the robot is reachable (`ssh navbot-pi 'echo ok'`); if not, say so and stop.

```bash
ssh navbot-pi 'bash -s' <<'EOF'
echo "== systemd units (P7 autostart, if installed) =="
for u in navbot-bringup navbot-web navbot-voice navbot-nav; do
  state=$(systemctl is-active "$u.service" 2>/dev/null || echo "absent")
  printf "  %-18s %s\n" "$u" "$state"
done
echo "== voice loop process =="
pgrep -af "navbot_voice_io.buddy_brain" || echo "  (buddy_brain not running as a bare process)"
echo "== buddy serial link =="
ls /dev/ttyACM* 2>/dev/null || echo "  no ttyACM* (buddy unplugged?)"
echo "== web control surface =="
for p in 8080 8081; do
  curl -fsS "http://127.0.0.1:$p/api/status" >/dev/null 2>&1 \
    && { echo "  /api/status OK on :$p"; break; } \
    || echo "  no /api/status on :$p"
done
EOF
```

Interpret: a healthy autostarted appliance shows `navbot-bringup`, `navbot-web`,
`navbot-voice` all **active** (`navbot-nav` **absent/inactive** is expected — it
needs a home map). Manual operation instead shows `buddy_brain` as a running
process and `/api/status OK`. Follow live logs with
`journalctl -u navbot-voice.service -f`. To halt: `/navbot:stop`.
