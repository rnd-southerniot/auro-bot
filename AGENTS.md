# AGENTS.md

## Startup rule

When resuming work in this repo, read these first:

1. `README.md`
2. `docs/index.md`
3. `docs/RUNBOOK.md`
4. `docs/project-status.md`
5. `docs/validation/README.md`
6. `TODO.md`

## Canonical working copy

The canonical runtime/development working copy is the Pi repo:

```bash
/home/arif/projects/makerpi-rp2040-ros2-navbot
```

The laptop repo is useful for support/editing, but robot runtime truth should be treated as Pi-first.

## Runtime truth

The currently validated LiDAR runtime on the Pi is not yet fully self-contained inside this repo.

The working path currently depends on sourcing:

```bash
/home/arif/ros2_ws/install/setup.bash
```

because that overlay provides the working `sllidar_ros2` runtime.

Do not silently remove or ignore that dependency when resuming work.

## Working style

- Preserve validated hardware/runtime facts in repo files, not only in chat
- Distinguish clearly between:
  - validated now
  - pending validation
- Do not overclaim production readiness
- Do not jump into aggressive autonomy/Nav2 work before dependency cleanup and calibration review
- If new hardware/runtime truths are confirmed, update:
  - `docs/architecture/system.md`
  - `docs/validation/README.md`
  - `docs/RUNBOOK.md`
