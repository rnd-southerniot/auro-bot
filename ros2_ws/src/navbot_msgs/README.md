# navbot_msgs

Reserved package namespace for future Navbot custom ROS 2 messages.

## Current state

Placeholder. The `msg/` directory exists but contains no message
definitions. There is no `package.xml` — this package does **not**
build. It is a namespace reservation only; do not import it.

When a custom message type is needed (e.g. a richer controller-state
struct than the current `std_msgs/String` JSON envelope), add the
`package.xml`, `CMakeLists.txt`, and `.msg` files here rather than
scattering message types across feature packages.

## See also

- [../../README.md](../../README.md) — workspace-level package list.
