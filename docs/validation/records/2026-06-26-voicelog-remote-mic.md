# Voicelog remote push-to-talk mic — second audio source (validation)

**Date:** 2026-06-26
**Scope:** A separate battery device (`voicelog-fw`) repurposed as a roaming
push-to-talk mic that streams PCM to the robot's voice brain over TCP, alongside
the on-robot buddy mic; the buddy keeps the speaker.
**Stack:** robot `navbot-pi` (autostart appliance), `navbot_voice_io` with the new
`remote_mic` listener; voicelog on ESP-IDF v5.4, firmware `0.3.0-livemic`.
**Verdict:** END-TO-END HARDWARE-VALIDATED (mic → robot → buddy speaker), with one
known network caveat (camera IP clash, below).

## Architecture (as built)

- **voicelog-fw** (`feat/livemic`, merged): tap BOOT → `livemic` connects to
  `<host::ip>:<port>` (NVS; set `192.168.68.126:8079`) and streams
  `START<device_id>` → N×`AUDIO<pcm>` → `END` (1-byte type + 4-byte BE len +
  payload), 16 kHz/16-bit mono — identical to the buddy mic. Non-blocking connect
  (2 s) so a blocked/absent target fails fast.
- **navbot_voice_io** (`feat/remote-mic`, merged): `remote_mic.py` TCP listener on
  `NAVBOT_REMOTE_MIC_PORT` (8079); `buddy_brain` feeds both mics into a single
  worker queue → one utterance at a time (single robot body; STT/Claude serial).
  Replies always go out the buddy speaker; on-device "stop" path unchanged.

## What was validated on hardware (2026-06-26)

1. **Transport** (voicelog → listener), gateway standing in: tap → 6.3 s of real
   speech (rms 920) received as START/AUDIO/END.
2. **Robot pipeline** (listener → STT → brain → speaker), replay to `navbot-pi`:
   `heard [voicelog:replaytest]: 'Hello microphone testing …'` →
   `reply: 'Loud and clear …'` (spoken on the buddy).
3. **Full real device → robot → buddy speaker** (voicelog PTT, `dev=3cdc755950d0`):
   - "drive backward for 5 seconds" → moved briefly, reply *"…I keep each move
     short for safety so I can't do a full five-second reverse"* (SafetyGate budget
     honored from the voicelog mic).
   - "search my chair / find the door" → robot spun 360° (closed-loop turn), reply
     noted the camera wasn't responding (see caveat).
   Source-tagging (`voicelog:<id>`) and the one-at-a-time queue both confirmed.

## Boot-readiness

`navbot-voice` is **enabled**; `NAVBOT_REMOTE_MIC_PORT=8079` in
`/etc/navbot/navbot.env`; `remote_mic.py` is in the built `install/`. On boot the
voice stack comes up with **both** mics ready (buddy "Jarvis" + voicelog PTT).

## Deploy note

Robot is colcon-built **without** `--symlink-install`; deploy = scp
`remote_mic.py` + `buddy_brain.py` to robot src → `colcon build
--packages-select navbot_voice_io` → restart `navbot-voice`. Robot has no host
firewall (ufw inactive), so 8079 is open — unlike the gateway, whose ufw
`INPUT DROP` blocked 8079 and cost us a debugging detour. See [[robot-ros-deploy]].

## Known caveat / follow-up

- **Camera IP clash:** the voicelog grabbed `192.168.68.107` (the camera's DHCP
  reservation) while the camera was off; with both powered the **camera can't
  reclaim `.107` and is offline**, so visual-search commands spin but see nothing.
  Fix (owner: operator): add a DHCP reservation for the voicelog MAC
  `3C:DC:75:59:50:D0` to a free IP so the camera regains `.107`.
- voicelog build needs **ESP-IDF v5.4** (v6 dropped `json`/`mqtt` from core).
