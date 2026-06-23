# Aurbot STEM Academy — Internal Training Curriculum

## Program: Autonomous Navigation Robot — From BOM to Cloud

**Target audience:** Early-career engineers at Southern IoT (1-3 years experience)
**Format:** Internal team training, informal, project-based
**Delivery:** Self-paced with weekly check-ins + lab sessions
**Duration:** 12 weeks (2 evenings/week lab time + self-study)
**Outcome:** Each engineer builds and deploys a fully autonomous
navigating robot with IoT telemetry integration

**Philosophy:** You learn by building. Every module ends with a working
subsystem, not a slideshow. The robot accumulates capability week by
week — by the end, it navigates autonomously, reports telemetry over
LoRaWAN, and integrates with Southern IoT's CRM platform.

---

## Bill of Materials (Per Engineer)

### Core Platform

| # | Component | Specification | Est. Cost (BDT) | Source |
|---|-----------|--------------|-----------------|--------|
| 1 | Raspberry Pi 5 (4GB) | Compute platform | 8,500 | Local/Import |
| 2 | Cytron Maker Pi RP2040 | Motor controller + IO | 2,200 | Cytron/AliExpress |
| 3 | Micro-metal gearmotors × 2 | 6V, 30:1, magnetic encoder | 3,000 | Cytron/Pololu |
| 4 | Wheels × 2 + caster × 1 | 65mm wheels, ball caster | 800 | Local |
| 5 | RPLIDAR C1 | 2D LiDAR, 360° | 8,500 | Slamtec/AliExpress |
| 6 | 9-DOF IMU (GY-80 or similar) | L3G4200D + LSM303DLHC | 600 | Local |
| 7 | INA238 breakout (Adafruit) | Current/voltage/power monitor | 1,800 | Adafruit/Import |
| 8 | Chassis plate | Acrylic or 3D-printed, 150×120mm | 500 | Local fab |

### Power System

| # | Component | Specification | Est. Cost (BDT) |
|---|-----------|--------------|-----------------|
| 9 | 18650 cells × 6 | 3.7V 2600mAh (4S Pi pack + 2S LiDAR pack) | 1,800 |
| 10 | Battery holders (4S + 2S) | With leads | 300 |
| 11 | Fulree buck converter | F35J5V20A5L 5V 20A | 900 |
| 12 | 12V-5V buck converter | Generic, for LiDAR | 200 |
| 13 | 5V battery pack | For motor rail (4× AA or USB power bank) | 400 |
| 14 | Power switches × 3 | One per battery system | 150 |

### Connectivity & Accessories

| # | Component | Specification | Est. Cost (BDT) |
|---|-----------|--------------|-----------------|
| 15 | MicroSD card (64GB) | For Pi OS | 600 |
| 16 | STEMMA QT cables × 2 | I²C interconnect | 400 |
| 17 | Jumper wires, headers, screws | Assorted | 500 |
| 18 | USB-C cable + power adapter | For Pi development | 500 |

### Optional / Phase 2

| # | Component | Purpose | Est. Cost (BDT) |
|---|-----------|---------|-----------------|
| 19 | RAK3172 LoRaWAN module | IoT telemetry uplink | 1,500 |
| 20 | Second INA238 breakout | Pi rail monitoring | 1,800 |
| 21 | Camera module (Pi Camera v3) | Visual navigation (future) | 4,500 |

**Total core BOM:** ~31,150 BDT (~$260 USD) per robot

---

## Curriculum Structure

### Pre-requisites (self-study before Week 1)

Engineers should be comfortable with:
- Linux command line (ssh, file navigation, package management)
- Python basics (functions, classes, file I/O)
- Git fundamentals (clone, branch, commit, push)
- Basic electronics (voltage, current, resistance, I²C concept)
- Soldering (through-hole, basic SMD rework)

**Provided resources:**
- Southern IoT onboarding docs (internal)
- ROS 2 Humble/Jazzy tutorials (docs.ros.org) — read, don't do yet
- Cytron Maker Pi RP2040 getting-started guide

---

### Module 1: Hardware Assembly & Power Architecture (Week 1-2)

**Learning goals:**
- Assemble a differential-drive robot from components
- Design a multi-rail power system with isolation
- Understand power budgeting for battery-operated robots
- Learn measurement-first debugging (multimeter, I²C scan)

**Sessions:**

**Week 1, Session 1 — Chassis + Motors + Wheels (2 hr lab)**
- Assemble chassis plate with motor mounts
- Attach motors, wheels, caster
- Verify motor spin direction with direct battery connection
- Document motor polarity for each wheel

**Week 1, Session 2 — Power System (2 hr lab)**
- Build three-battery power architecture:
  - System 1: 4S 18650 → Fulree buck → 5.1V Pi rail
  - System 2: 2S 18650 → 12V-5V buck → LiDAR rail
  - System 3: 5V pack → Maker Pi RP2040 → motors
- Wire power switches per rail
- Test each rail independently with multimeter
- Learn: why three separate rails? (isolation, fault containment,
  independent shutdown)

**Week 2, Session 3 — Maker Pi RP2040 + Motor Test (2 hr lab)**
- Socket Pico/Pico W into Maker Pi RP2040
- Flash MicroPython
- Write first motor control script (forward, backward, stop)
- Understand motor driver truth table (Cytron datasheet Section 3)
- Learn: IN1=IN2=LOW is brake, IN1=IN2=HIGH is coast — not the same!
- Verify encoder signals with simple counter script

**Week 2, Session 4 — INA238 Current Monitor (2 hr lab)**
- Wire INA238 breakout to motor rail (high-side sensing)
- Write MicroPython I²C driver from register map (not a library!)
- Read bus voltage, shunt voltage, current, power
- Bench test: motor pulse + INA238 reading simultaneously
- Learn: SHUNT_CAL register, CURRENT_LSB, two's complement
- Learn: Multiple Power Input Selector gotcha — battery must exceed
  USB voltage for current to flow through shunt

**Deliverable:** Robot drives forward/backward via button press,
INA238 displays real-time current on serial console.

**Assessment:** Engineer demonstrates motor + current measurement
working. Explains power architecture and isolation rationale.

---

### Module 2: Pi Setup + ROS 2 Fundamentals (Week 3-4)

**Learning goals:**
- Set up Pi 5 with Ubuntu + ROS 2 Jazzy
- Understand ROS 2 concepts: nodes, topics, services, actions
- Build a serial bridge between Pi and RP2040
- Publish robot telemetry as ROS 2 topics

**Sessions:**

**Week 3, Session 5 — Pi OS + ROS 2 Install (2 hr lab)**
- Flash Ubuntu 24.04 Server to SD card
- Boot Pi, configure WiFi (netplan), set static IP
- Install ROS 2 Jazzy (apt)
- Verify: `ros2 topic list`, `ros2 node list`
- Learn: why Ubuntu Server not Desktop? (headless robot, SSH-only)

**Week 3, Session 6 — First ROS 2 Nodes (2 hr lab + self-study)**
- Write a Python publisher node (publishes "hello" at 1 Hz)
- Write a subscriber node (prints received messages)
- Understand QoS, topic types, message definitions
- Run both nodes, verify with `ros2 topic echo`
- Self-study: ROS 2 launch files, parameter files

**Week 4, Session 7 — Serial Bridge (2 hr lab)**
- Design serial protocol between Pi and RP2040
- Implement RP2040 side: send encoder ticks + battery voltage
- Implement Pi side: ROS 2 node that reads serial, publishes topics
- Topics: /base/encoder_left, /base/encoder_right, /base/motor_voltage
- Learn: baud rate selection, packet framing, error handling

**Week 4, Session 8 — Cmd_vel + Diff-Drive Kinematics (2 hr lab)**
- Implement cmd_vel subscriber on Pi → serial command to RP2040
- RP2040 receives velocity commands, applies diff-drive kinematics
- Forward/inverse kinematics: (v, ω) ↔ (v_left, v_right)
- Test: `ros2 topic pub /cmd_vel` → robot moves
- Learn: wheel_radius and wheel_separation matter — measure them!

**Deliverable:** Robot drives via ROS 2 cmd_vel. Telemetry (encoders,
voltage) visible as ROS 2 topics. Serial bridge reliable.

**Assessment:** Engineer teleops robot via cmd_vel, explains diff-drive
kinematics, shows telemetry topics in terminal.

---

### Module 3: Odometry + URDF + TF (Week 5-6)

**Learning goals:**
- Compute wheel odometry from encoder data
- Build a URDF model of the robot
- Understand the ROS 2 TF tree
- Calibrate wheel_radius and wheel_separation empirically

**Sessions:**

**Week 5, Session 9 — Wheel Odometry (2 hr lab)**
- Implement odometry computation from encoder deltas
- Publish /odom (nav_msgs/Odometry) + odom→base_link TF
- Test: drive 1 m forward, compare odom to tape measure
- Learn: dead reckoning drift, why it accumulates

**Week 5, Session 10 — URDF Robot Model (2 hr lab + self-study)**
- Write XACRO/URDF for the robot: base_link, wheels, caster,
  laser_link, imu_link
- Launch robot_state_publisher
- Visualize in Foxglove or rviz2
- Learn: base_footprint vs base_link (2D nav convention)

**Week 6, Session 11 — Calibration Sprint (2 hr lab)**
- Drive 1 m: measure odom vs tape → calibrate wheel_radius
- Rotate 360°: measure odom vs physical → calibrate wheel_separation
- Fix URDF to match measurements
- Learn: 1.5% wheel_radius error causes visible path curvature
  (the Navbot's real finding from Session 8)

**Week 6, Session 12 — Foxglove Dashboard (2 hr lab)**
- Install foxglove_bridge on Pi
- Configure Foxglove Studio on laptop
- Build a dashboard: odom trail, TF tree, laser scan, topics panel
- Save layout to repo (reproducible across team)

**Deliverable:** Robot publishes accurate odometry, URDF renders
correctly in Foxglove, wheel parameters are empirically calibrated.

**Assessment:** 360° rotation test: odom reports 360° ± 5°. Engineer
explains TF tree and calibration methodology.

---

### Module 4: LiDAR + SLAM (Week 7)

**Learning goals:**
- Integrate RPLIDAR C1 with ROS 2
- Understand occupancy grid mapping
- Run SLAM Toolbox for online mapping
- Save and load maps

**Sessions:**

**Week 7, Session 13 — LiDAR Integration (2 hr lab)**
- Wire RPLIDAR C1 (5V, USB or UART)
- Install and launch rplidar_ros2 driver
- Verify /scan topic in Foxglove (360° scan visualization)
- Add laser_filters: +Inf → NaN, range cap at 16 m
- Learn: LiDAR mounting orientation matters (arrow direction)

**Week 7, Session 14 — SLAM + Map Save/Load (2 hr lab)**
- Launch SLAM Toolbox (online async mode)
- Drive robot around room, watch map build in Foxglove
- Save map: map_saver_cli
- Load map: map_server + AMCL localization
- Learn: SLAM vs localization — when to use which

**Deliverable:** Robot builds a map of the lab, saves it, and
re-localizes against the saved map on next boot.

**Assessment:** Engineer demonstrates map building, saving, loading,
and AMCL localization. Explains the difference between SLAM and AMCL.

---

### Module 5: Navigation (Week 8-9)

**Learning goals:**
- Configure and run Nav2 for autonomous navigation
- Understand costmaps, planners, and controllers
- Tune controller parameters for robot-specific motor envelope
- Achieve first autonomous navigation goal

**Sessions:**

**Week 8, Session 15 — Nav2 Setup (2 hr lab)**
- Install Nav2 packages
- Configure nav2_params.yaml: costmaps, planner, controller
- Launch full Nav2 stack
- Understand lifecycle nodes — why they need explicit activation
- Learn: inflation_radius must match robot footprint, not arbitrary

**Week 8, Session 16 — Controller Tuning (2 hr lab)**
- Measure motor minimum reliable velocity (stepped cmd_vel test)
- Choose controller: DWB vs RegulatedPurePursuitController (RPP)
- Tune velocity parameters to match motor envelope
- Learn: DWB trajectory scoring vs RPP geometric tracking
- Learn: the Navbot's real finding — DWB's weighted-critic scoring
  (ObstacleFootprint, GoalDist, PathDist, RotateToGoal…) can produce
  a rotation-only local minimum on diff-drive robots, even with a
  verifiably clear forward corridor. Reducing inflation_radius and
  sim_time did not unblock forward motion; switching DWB → RPP did.
  Critic-balance tuning is fragile per-platform; RPP's geometric
  pure-pursuit approach maps more naturally to diff-drive.

**Week 9, Session 17 — First Navigation Goal (2 hr lab)**
- Send navigate_to_pose goal (1 m forward)
- Observe: planning, execution, arrival, goal_checker
- Tune xy_goal_tolerance and yaw_goal_tolerance
- Try goals with turns (rotation + translation)
- Learn: terminal rotation overshoot and damping

**Week 9, Session 18 — Multi-Waypoint Route (2 hr lab)**
- Write a waypoint navigation script (nav2_simple_commander)
- Define 3-4 waypoints in saved map
- Run autonomous route: A → B → C → Home
- Measure return-to-origin accuracy
- Learn: localization drift over sustained autonomy

**Deliverable:** Robot navigates autonomously through multiple
waypoints and returns to start position.

**Assessment:** Engineer runs a 4-waypoint route. Robot completes
all legs. Return-to-origin XY error < 10 cm.

---

### Module 6: IMU + Sensor Fusion (Week 10)

**Learning goals:**
- Read IMU data from I²C (raw register access)
- Understand accelerometer, gyroscope, magnetometer roles
- Implement ROS 2 IMU driver from datasheet
- Fuse IMU + wheel odometry via EKF

**Sessions:**

**Week 10, Session 19 — IMU Driver from Scratch (2 hr lab)**
- Read WHO_AM_I registers to identify chips
- Write Python I²C driver for gyro (L3G4200D) + accel (LSM303DLHC)
- Publish /imu/data_raw at 50 Hz
- Learn: axis mapping (ROS convention: X forward, Y left, Z up)
- Learn: verify axis mapping empirically, don't guess from datasheet

**Week 10, Session 20 — Sensor Fusion (2 hr lab)**
- Configure imu_complementary_filter (gyro + accel, no mag near motors)
- Configure robot_localization EKF (fuse /odom + /imu/data)
- Switch Nav2 to /odometry/filtered
- Benchmark: 360° rotation heading drift — EKF vs encoder-only
- Learn: magnetometer near motors = distorted heading (the Navbot's
  real finding from Session 10)

**Deliverable:** EKF publishing `/odometry/filtered` at 30 Hz,
owning the `odom → base_footprint` TF, Nav2 consuming fused odom.

**Assessment:** **Spin-and-return (CCW then CW) drift test.** Robot
spins +0.5 rad/s × T seconds, then -0.5 rad/s × T seconds; end yaw
should equal start yaw regardless of rotation amount. On a calibrated
chassis, wheel-only odometry returns within **0.5° per round-trip**
(the Navbot's Session 10 measurement: 0.36° ± 0.18°). Gyro+accel EKF
matches within ~1° on the same test.

**A critical "why" lesson from Session 10:** straight-line 360°-open-
loop rotation benchmarks are ambiguous because rotation amount varies
with motor ratio. Spin-and-return isolates drift from command-rotation
scaling and is the right benchmark. Also, magnetometer fusion near
motors (`use_mag: true`) made heading *worse* during motion — EKF
round-trip drift ballooned to 9.7° with high per-trial variance due
to motor-coil EM distorting the mag field. The Navbot's reference
config runs `use_mag: false` until the IMU can be relocated further
from the motor stack.

---

### Module 7: Counter-Drive Firmware (Week 11)

**Learning goals:**
- Design a firmware-level state machine for motor control
- Implement hardware watchdog safety mechanisms
- Bench-validate before floor-testing (the discipline)
- Measure and characterize counter-drive performance

**Sessions:**

**Week 11, Session 21 — FSM Design + Implementation (3 hr lab)**
- Design per-motor counter-drive FSM:
  IDLE → NORMAL → DECEL_MON → COUNTER_DRIVE_ACTIVE → (IDLE | FAULT)
- Implement with compile-time disable flag
- Hardware watchdog via RP2040 alarm timer
- Shared abort between motors
- Learn: why 15% PWM cap? (computed from motor stall current + driver rating)
- Learn: encoder-gated termination — stop when velocity says stop,
  not after a fixed duration

**Week 11, Session 22 — Bench + Floor Validation (3 hr lab)**
- Flash firmware with CD enabled
- Bench: lifted wheels, per-motor test, observe state transitions
- Floor: 5 trials at 0.05 m/s, measure coast-on reduction
- Compare: 17 mm → sub-1 mm coast (the Navbot's result)
- Learn: brake (IN1=IN2=LOW) vs coast (IN1=IN2=HIGH) vs counter-drive
  (reverse PWM). Why brake doesn't work at low speeds.

**Deliverable:** Counter-drive firmware active, coast-on reduced
by > 90% at 0.05 m/s.

**Assessment:** 5-trial floor test showing statistically significant
coast-on reduction. Engineer explains FSM states, safety layers,
and why the PWM cap value was chosen.

---

### Module 8: IoT Integration — LoRaWAN Telemetry (Week 12)

**Learning goals:**
- Connect a LoRaWAN module to the robot
- Transmit robot telemetry (battery voltage, position, status)
  over LoRaWAN to ChirpStack
- View telemetry in Southern IoT's CRM dashboard
- Understand the full embedded-to-cloud data path

**Sessions:**

**Week 12, Session 23 — RAK3172 + ChirpStack (2 hr lab)**
- Wire RAK3172 LoRaWAN module to Pi (UART or USB)
- Register device on ChirpStack (DevEUI, AppKey, device profile)
- Join the AS923 LoRaWAN network
- Send a test uplink payload
- Learn: LoRaWAN join flow, frame counters, duty cycle

**Week 12, Session 24 — Robot Telemetry Pipeline (2 hr lab)**
- Write a ROS 2 node that subscribes to robot topics:
  /power/ina238/bus_voltage_v, /odometry/filtered, /base/controller_state
- Encode telemetry as CayenneLPP or custom payload
- Transmit at configurable interval (e.g., every 30 seconds)
- View on ChirpStack device dashboard
- Forward to Southern IoT CRM via MQTT integration
- Learn: payload encoding tradeoffs (CayenneLPP vs custom)
- Learn: LoRaWAN is for telemetry, not control (latency too high)

**Deliverable:** Robot reports battery voltage, position, and
operational status over LoRaWAN to ChirpStack, visible in CRM.

**Assessment:** Engineer demonstrates end-to-end data flow:
robot sensor → ROS 2 topic → LoRaWAN uplink → ChirpStack →
MQTT → CRM dashboard. Explains each hop.

---

## Capstone Project (Post-Week 12)

Each engineer proposes and implements one enhancement:

**Suggested capstone topics:**
- **Autonomous patrol route** — robot navigates a predefined path,
  reports position + battery via LoRaWAN every lap
- **Obstacle avoidance tuning** — test in a cluttered environment,
  tune costmap for reliable navigation among furniture
- **Fleet coordination** — two robots sharing a map, avoiding
  each other (requires MQTT coordination)
- **Visual navigation** — add Pi Camera, implement visual odometry
  or object detection (advanced)
- **Custom sensor integration** — add environmental sensors (temp,
  humidity, air quality) and report via LoRaWAN
- **Power optimization** — benchmark battery life under different
  navigation patterns, implement sleep modes

**Capstone assessment:** 30-minute demo + 10-minute Q&A with
the team. Code committed to the engineer's own fork of the
claude-navbot repo.

---

## Teaching Methodology

### The "Build, Break, Fix, Document" Cycle

Each module follows this pattern:
1. **Build** — engineer builds the subsystem from components/code
2. **Break** — something won't work (by design or by accident)
3. **Fix** — debug using measurement, datasheets, logs
4. **Document** — write what happened, why it broke, how it was fixed

This mirrors real engineering practice. The Navbot's development
history is full of examples:
- INA238 reading zero → power-path bypass via USB (build, break, fix)
- Brake attempt ineffective → actually coast, not brake (build, break, fix)
- DWB rejecting forward paths → inflation radius too aggressive (build, break, fix)
- Magnetometer near motors → heading distortion (build, break, learn)

Students should expect things to not work on the first try. The
skill being developed is debugging methodology, not memorization.

### Evidence-Based Engineering

Every claim must be supported by measurement:
- "The motor draws 150 mA" → show the INA238 reading
- "Wheel_radius is 0.0325 m" → show the 1 m drive test vs tape
- "Counter-drive reduces coast by 97%" → show the 5-trial statistics
- "The IMU improves heading" → show before/after 360° benchmark

No handwaving. No "it seems to work." Data or it didn't happen.

### Commit Discipline

From Module 2 onward, all work is committed to git:
- Atomic commits with descriptive messages
- Each commit builds and runs (no broken intermediate states)
- Validation data committed alongside code changes
- Docs updated in the same commit as the code they describe

This isn't process overhead — it's the skill that makes engineers
productive in teams.

### The Session Prompt Pattern

Advanced modules (5+) use Claude Code or similar AI tools for
session execution. Engineers learn the structured prompt pattern:
- Context block (what's known, what was tried, what failed)
- Hard rules (safety constraints, review gates)
- Phase-gated steps with explicit pass/fail criteria
- Commit message templates with verification data

This is a transferable skill for any AI-assisted engineering workflow.

---

## Assessment Framework

### Per-Module Assessment

| Criterion | Weight | Method |
|-----------|--------|--------|
| Working subsystem | 40% | Live demo |
| Understanding (can explain why) | 30% | Q&A during demo |
| Code quality + commits | 15% | Code review |
| Documentation | 15% | Written validation record |

### Overall Program Assessment

| Milestone | Criteria |
|-----------|----------|
| Hardware complete | Robot drives via button press, current monitored |
| ROS 2 integration | Cmd_vel works, telemetry topics publishing |
| Navigation capable | Autonomous goal navigation with saved map |
| IoT connected | Telemetry visible in CRM dashboard |
| Capstone complete | Enhancement demo + code committed |

### Pass Criteria

Engineer passes the program if:
- All 8 module assessments completed (≥ 70% each)
- Capstone demo completed
- Robot is operational end-to-end (drives, navigates, reports telemetry)
- All code committed to personal fork with clean history

---

## Instructor Notes

### Common Failure Points (from Navbot development experience)

| Module | Likely failure | Root cause | Fix |
|--------|---------------|------------|-----|
| 1 | INA238 reads zero | USB power bypasses shunt | Raise battery voltage above USB |
| 2 | Serial bridge drops data | Baud rate mismatch or no framing | Add packet framing with checksum |
| 3 | Odom drifts badly | wheel_radius or wheel_separation wrong | Calibration sprint (measure, don't guess) |
| 4 | SLAM map has artifacts | +Inf LiDAR beams, no range filter | Add laser_filters node |
| 5 | Nav2 won't move forward | Costmap inflation too aggressive | Reduce inflation_radius to match footprint |
| 5 | DWB prefers rotation only | DWB critic-balance can produce a rotation-only local minimum on diff-drive, even with a clear forward corridor (costmap tuning alone may not fix) | Switch to RPP |
| 6 | Magnetometer distorts heading | Motors generate EM field | Set use_mag: false, use gyro+accel only |
| 7 | Counter-drive not firing | STOP handler resets CD state | Remove CD reset from STOP path |
| 8 | LoRaWAN join fails | Wrong AppKey or frequency plan | Verify ChirpStack device profile matches |

### Equipment Per Lab Station

- 1 × robot kit (BOM above)
- 1 × laptop with Ubuntu or macOS (for SSH + Foxglove)
- 1 × multimeter (essential for power debugging)
- 1 × USB-serial adapter (backup for RP2040 console)
- Soldering station (shared, Modules 1-2 only)
- 3 × 3 m clear floor space per robot (Modules 5+)
- WiFi access point (all modules)
- LoRaWAN gateway in range (Module 8 only)

### Time Budget Reality

The "2 hr lab" sessions assume engineers arrive prepared (self-study
done, components staged). If engineers need more time:
- Module 1-2: budget extra 2 hours for soldering/wiring mistakes
- Module 5: budget extra 4 hours for Nav2 config debugging
- Module 7: budget extra 2 hours for firmware build toolchain setup
- Module 8: budget extra 2 hours for ChirpStack admin setup

Total realistic time: 60-80 hours per engineer including self-study.

---

## Repository Structure for Training

Each engineer forks the template repo and works in their own fork:

```
aurbot-training-<name>/
├── firmware/           # RP2040 firmware (Modules 1, 2, 7)
├── ros2_ws/src/
│   ├── aurbot_base/    # Serial bridge, cmd_vel (Modules 2-3)
│   ├── aurbot_imu/     # IMU driver (Module 6)
│   ├── aurbot_navigation/ # Nav2 config (Module 5)
│   └── aurbot_telemetry/  # LoRaWAN node (Module 8)
├── maps/               # Saved SLAM maps (Module 4)
├── scripts/            # Test scripts, calibration tools
├── docs/
│   ├── assembly/       # Build photos, wiring diagrams
│   ├── calibration/    # Measurement data, parameter derivations
│   ├── testing/        # Validation records per module
│   └── project-status.md
└── CLAUDE.md           # AI assistant session prompts (Module 5+)
```

The template repo provides:
- BOM with links and prices
- Wiring diagrams for each module
- Stub files for each ROS 2 package (engineers fill in the implementation)
- Test scripts for each module assessment
- Reference solutions (in a separate branch, not visible by default)

---

## Schedule Overview

| Week | Module | Key Milestone |
|------|--------|---------------|
| 1 | 1: Hardware | Chassis assembled, power system working |
| 2 | 1: Hardware | Motors drive via MicroPython, INA238 reads current |
| 3 | 2: ROS 2 | Pi running ROS 2, first publisher/subscriber |
| 4 | 2: ROS 2 | Serial bridge working, cmd_vel drives robot |
| 5 | 3: Odom+URDF | Odometry publishing, URDF in Foxglove |
| 6 | 3: Odom+URDF | Calibrated wheel params, Foxglove dashboard |
| 7 | 4: LiDAR+SLAM | Map built, saved, re-localized |
| 8 | 5: Navigation | Nav2 configured, controller tuned |
| 9 | 5: Navigation | First nav goal, multi-waypoint route |
| 10 | 6: IMU | IMU driver + EKF fusion working |
| 11 | 7: Counter-Drive | FSM implemented, bench + floor validated |
| 12 | 8: LoRaWAN | End-to-end telemetry to CRM |
| 13+ | Capstone | Individual enhancement project |

---

## Connection to Southern IoT Business

This training program directly builds skills needed for Southern IoT's
core business:

| Training skill | Business application |
|----------------|---------------------|
| LoRaWAN integration | Device provisioning, fleet management |
| ROS 2 architecture | Industrial robot/AGV deployments |
| Power system design | Battery-operated IoT device design |
| I²C sensor integration | Environmental monitoring products |
| SLAM/Navigation | Warehouse automation, security patrol |
| EKF sensor fusion | Precision agriculture, asset tracking |
| Firmware state machines | Edge device reliability |
| AI-assisted development | Faster prototyping, documentation |
| Evidence-based debugging | Production incident response |
| Git discipline | Team collaboration at scale |

The robot is the vehicle. The engineering skills are the cargo.
