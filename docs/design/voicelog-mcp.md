# Design: voicelog ↔ MCP — voice front-end + MCP-managed device

> Status: planned 2026-06-27; Stage 1 in progress. Implementation notes will be
> appended / a validation record added under `docs/validation/records/`.

## Context

The SIoT **MCP gateway** (custom Python FastMCP aggregator) runs on the user's
**VM at `10.10.8.113:8000`**. It registers "upstream" MCP servers in
`proxy-config.json` (`servers[]`: name/url/prefix) and exposes them to clients via
the `discover_upstream_tools` / `call_upstream_tool` meta-tools. Goal: make the
battery **voicelog** device (ESP32-S3, `rnd-southerniot/voicelog-fw`) **both**:

1. a **voice front-end to MCP** — speak an instruction → routed through the gateway
   to *any* MCP-connected device/upstream (e.g. query SIoT device status) → the
   answer shows on the voicelog **OLED**; and
2. an **MCP-managed device** — MCP tools to operate/query the voicelog itself.

**Placement:** the voicelog logic runs on **the gateway Pi** (`mcp-gateway`,
`192.168.68.109`), which uniquely bridges both networks — `wlan0` on the robot LAN
(reaches the voicelog `192.168.68.117`) and `wg1` WireGuard `10.10.60.5` (reached by
the VM). It is registered as an **upstream** on the VM gateway; the VM cannot reach
the robot LAN directly, so the Pi is the bridge/proxy.

**Reply path:** voicelog **OLED** (SSD1306). **Device control transport:** **MQTT
command-subscribe** (firmware add). Note: the current `livemic` build does **not**
start MQTT (`app_main.c` dropped `net_mqtt_init`), so MQTT is re-enabled too.

**Broker:** run a **local mosquitto broker on the Pi**; point the voicelog at it
(`mqtt_uri_set mqtt://192.168.68.109:1883`, same LAN). The Pi MCP server uses the
same local broker. Avoids cross-subnet routing surprises (the stock default broker
`10.10.8.140` may not be reachable from the robot LAN).

## Stage 1 — voicelog as an MCP-managed device (control + query + OLED reply)

**A. Firmware** (`voicelog-fw`, ESP-IDF v5.4, flash from the Pi):
- Re-enable `net_mqtt_init()` in `main/app_main.c` (keep `livemic`).
- `main/net_mqtt.c`: subscribe `voicelog/<id>/cmd` (QoS 1); handle
  `MQTT_EVENT_MESSAGE` → parse JSON `{"action":…}` (cJSON) → dispatch; publish
  acks/results to `voicelog/<id>/cmdresp`.
- Handlers: `oled {text,secs?}` (OLED reply), `status`, `list_clips`, `set_host
  {ip,port}` (reuse `host_set` NVS logic), `reboot`.
- OLED text mode in `main/display.h` + `display_ssd1306.c`
  (`display_show_text(text, secs)` / `DISP_TEXT`).

**B. Pi broker + MCP server:**
- mosquitto on the Pi; ufw allow `1883` from `192.168.68.0/22`.
- `~/mcp-gateway/voicelog-server/server.py` — FastMCP (mirror
  `~/mcp-gateway/local-server/server.py`), `paho-mqtt` to the local broker. Query:
  `voicelog_status/events/list_clips`; control: `voicelog_show_text/set_host/reboot`.
  systemd unit (mirror `mcp-local.service`) on `:8002`; ufw allow `8002` from the WG
  subnet.

**C. Register upstream on the VM** (`proxy-config.json` `servers[]`):
`{"name":"voicelog","url":"http://10.10.60.5:8002","prefix":"voicelog",…}` + reload.

## Stage 2 — voicelog as a voice front-end to the MCP ecosystem

Pi-side MCP voice agent: point voicelog `host_set` at the Pi → `remote_mic` listener
(reuse `navbot_voice_io/remote_mic.py`) → faster-whisper STT → headless Claude Code
agent wired to the VM gateway (`.mcp.json` → `10.10.8.113:8000/mcp`) → query/operate
any upstream → push the short answer to the voicelog OLED via the Stage‑1 cmd path.

## Verification

1. `mosquitto_pub -t voicelog/3cdc755950d0/cmd -m '{"action":"oled","text":"hello"}'`
   on the Pi → OLED shows it; `mosquitto_sub -t 'voicelog/+/status'` shows status.
2. Via the VM gateway: `call_upstream_tool("voicelog","voicelog_status")` /
   `voicelog_show_text` / `voicelog_list_clips`.
3. Stage 2: voicelog PTT "status of <device>" → STT → agent → gateway → OLED answer.

## Notes / open items

- VM↔Pi over WireGuard; open Pi ufw `8002` for the WG subnet; upstream URL assumed
  `http://10.10.60.5:8002` (Pi `wg1` IP).
- Proxy authenticates *clients* (bearer token); internal upstreams run unauthenticated
  on the trusted WG/LAN (locked down by ufw), like `local-pi` `:8001`.
- Voicelog reserved at `192.168.68.117`; device_id `3cdc755950d0`.
- OLED 128×64 → short replies; summarize/scroll long answers.
