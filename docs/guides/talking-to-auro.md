# Talking to Auro — user guide

A friendly "what do I say" guide for driving the robot, using its camera, and
searching for things — all by voice. No terminal needed. For the technical/ops
version (ssh, curl, logs, troubleshooting) see
[../operations/voice-appliance.md](../operations/voice-appliance.md).

## 1. Get it ready

1. **Power on the robot** and the **camera** (the small camera board has its own
   power; give it ~20 s to join Wi-Fi). The robot starts everything itself on
   boot — no buttons to press.
2. **Decide: drive or not.** If you want it to *move*, set it on **open floor**
   (or up on **blocks** for a safe test). Keep the path clear of feet, pets,
   cables, and stairs. If you only want to talk/look, anywhere is fine.
3. Wait until it's ready (about a minute). It's listening when it shows its
   **idle face**.

## 2. The three golden rules

1. **Start every command with "Jarvis."** Say it clearly — wake works best at
   normal volume (it has one little mic).
2. **One request per "Jarvis."** Wait for the **listening face**, say your one
   thing, then wait for the spoken reply.
3. **"Jarvis, stop" any time.** Saying **stop** halts it instantly. For a true
   emergency, hit the **hardware e-stop** — that always works.

## 3. Drive it by voice

Tell it where to go in plain words. It enables motion itself and **keeps every
move short and slow for safety** — it won't do long runs even if you ask.

| Say | What happens |
|---|---|
| "Jarvis, **drive forward** for two seconds" | rolls forward gently (~0.10 m/s), then stops on its own |
| "Jarvis, **back up** a little" | a short reverse |
| "Jarvis, **turn left**" / "**turn right**" | a small in-place turn |
| "Jarvis, **turn around**" | rotates to roughly face the other way |

Good to know:
- It **caps how far it goes per command** (a few seconds of motion). Ask for
  "drive 40 seconds" and it does a short move and tells you it keeps moves brief.
- If it can't move it **says why** ("drive mode off", "e-stop is on", etc.).
- ⚠️ A "stop" shouted *in the middle* of a drive **might not be heard** yet — but
  moves are short and slow, and the **e-stop** always stops it.

## 4. Use the camera

The camera is the robot's eyes (it faces forward).

| Say | What happens |
|---|---|
| "Jarvis, **what do you see?**" | takes a photo and describes the scene in a sentence |
| "Jarvis, **describe the room**" | same idea — it answers from what's in front of it |

## 5. Search for something ("look for X")

Ask it to **find** a thing and it will **spin all the way around**, taking photos
as it goes, then **turn to face** the thing if it finds it.

| Say | What happens |
|---|---|
| "Jarvis, **look for my mug**" | spins 360°, and if it sees the mug, turns to face it and says where it is |
| "Jarvis, **find the chair**" | same — or "I looked all around and couldn't find it" |
| "Jarvis, **where is the door?**" | searches and points itself at it |

Tips: make sure the thing is **out where the camera can see it** (not hidden),
with decent light. The spin is **in place** — it looks around, it doesn't drive
over to the object.

## 6. Ask how it's doing

| Say | What happens |
|---|---|
| "Jarvis, **what's your status?**" | reports e-stop, battery/voltage, and sensors |
| "Jarvis, **is your LiDAR working?**" | tells you if the laser scanner is alive |

## 7. What it can't do (yet)

- **Go to a named place** ("go to the kitchen") — it has no map of your home yet.
- **Pick things up** — no arm.
- **Find things it can't see** — search only spots what's in camera view.

## 8. If something seems off

- **No response to "Jarvis"** — say it louder/clearer; try again. One request per wake.
- **"camera unavailable"** — the camera board may be off or off-Wi-Fi; check its power.
- **Won't drive** — it'll usually say why; make sure you asked it to move and
  nothing's blocking it.
- For anything deeper, hand it to an operator → see
  [../operations/voice-appliance.md](../operations/voice-appliance.md) and the
  bench self-tests (`/navbot:status`, `/navbot:voice-status`, `/navbot:stop`).
