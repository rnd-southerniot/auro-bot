#!/usr/bin/env python3
"""
Multi-waypoint autonomous route using nav2_simple_commander.

Reads the robot's current pose from TF as "home", then navigates
through a short square route and returns. Logs per-leg distance,
time, and Nav2 status. Reports total route error at the end
(how close the robot got back to home).

Waypoints are defined as offsets from home:
  A = home + (+0.6, 0.0) — east
  B = home + (+0.6, -0.6) — south-east
  C = home + ( 0.0, -0.6) — south
  return to home
"""
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from geometry_msgs.msg import PoseStamped
from tf2_ros import Buffer, TransformListener
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult


def yaw_from_quat(qx, qy, qz, qw):
    return math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))


def pose_stamped(x, y, yaw, stamp):
    p = PoseStamped()
    p.header.frame_id = "map"
    p.header.stamp = stamp
    p.pose.position.x = float(x)
    p.pose.position.y = float(y)
    z = math.sin(yaw / 2.0)
    w = math.cos(yaw / 2.0)
    n = math.sqrt(z * z + w * w)
    p.pose.orientation.z = z / n
    p.pose.orientation.w = w / n
    return p


class TFReader(Node):
    def __init__(self):
        super().__init__("multi_waypoint_tf_reader")
        self.buf = Buffer()
        self.tl = TransformListener(self.buf, self)

    def read_pose_map_base(self, timeout_s=5.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            try:
                tf = self.buf.lookup_transform("map", "base_footprint", rclpy.time.Time())
                q = tf.transform.rotation
                return (
                    tf.transform.translation.x,
                    tf.transform.translation.y,
                    yaw_from_quat(q.x, q.y, q.z, q.w),
                )
            except Exception:
                rclpy.spin_once(self, timeout_sec=0.2)
        return None


def main():
    rclpy.init()
    reader = TFReader()
    home = reader.read_pose_map_base()
    if home is None:
        print("ERROR: no map->base_footprint TF")
        rclpy.shutdown()
        return
    hx, hy, hyaw = home
    print(f"Home (current pose): map({hx:+.3f}, {hy:+.3f}, yaw={math.degrees(hyaw):+.1f}°)")

    # Waypoints: offsets from home in map-frame. Yaw for each
    # waypoint is the bearing from the previous waypoint (so the
    # robot roughly faces its direction of travel on arrival).
    def goal(dx, dy, dyaw):
        return (hx + dx, hy + dy, dyaw)

    waypoints = [
        ("A", goal(+0.6,  0.0, 0.0)),
        ("B", goal(+0.6, -0.6, -math.pi / 2)),
        ("C", goal( 0.0, -0.6, math.pi)),
        ("Home", (hx, hy, hyaw)),
    ]

    nav = BasicNavigator()
    # AMCL is already localized via /initialpose; skip setInitialPose.
    # Wait for Nav2 to be ready.
    nav.waitUntilNav2Active(localizer="amcl")

    print()
    print("=== Multi-waypoint route ===")
    results = []
    route_start = time.monotonic()

    for label, (x, y, yaw) in waypoints:
        cur = reader.read_pose_map_base(timeout_s=2.0)
        print(f"\n--- Leg to {label}: map({x:+.3f}, {y:+.3f}, yaw={math.degrees(yaw):+.1f}°)")
        if cur is not None:
            cx, cy, _ = cur
            dist = math.hypot(x - cx, y - cy)
            print(f"    from map({cx:+.3f}, {cy:+.3f})  ≈ {dist:.2f} m away")

        now = nav.get_clock().now().to_msg()
        goal_pose = pose_stamped(x, y, yaw, now)

        leg_t0 = time.monotonic()
        nav.goToPose(goal_pose)
        while not nav.isTaskComplete():
            rclpy.spin_once(reader, timeout_sec=0.1)
            fb = nav.getFeedback()
            # BasicNavigator feedback includes distance_remaining
            if fb and int(time.monotonic()) % 2 == 0:
                pass  # optional periodic status
        leg_t = time.monotonic() - leg_t0
        status = nav.getResult()
        end = reader.read_pose_map_base(timeout_s=2.0)
        status_name = {
            TaskResult.SUCCEEDED: "SUCCEEDED",
            TaskResult.CANCELED: "CANCELED",
            TaskResult.FAILED: "FAILED",
        }.get(status, str(status))
        if end is not None:
            ex, ey, eyaw = end
            xy_err = math.hypot(x - ex, y - ey)
            yaw_err = math.degrees(abs((yaw - eyaw + math.pi) % (2 * math.pi) - math.pi))
            print(f"    {status_name}  t={leg_t:.1f}s  end=({ex:+.3f},{ey:+.3f},{math.degrees(eyaw):+.1f}°)  "
                  f"xy_err={xy_err:.3f}m  yaw_err={yaw_err:.1f}°")
        else:
            print(f"    {status_name}  t={leg_t:.1f}s  end=(TF unavailable)")
        results.append((label, status_name, leg_t, end))

    route_t = time.monotonic() - route_start
    print()
    print("=" * 60)
    print(f"Route complete. Total time: {route_t:.1f}s")
    end = reader.read_pose_map_base(timeout_s=2.0)
    if end is not None:
        ex, ey, eyaw = end
        return_xy_err = math.hypot(hx - ex, hy - ey)
        return_yaw_err = math.degrees(abs((hyaw - eyaw + math.pi) % (2 * math.pi) - math.pi))
        print(f"Home was:  map({hx:+.3f}, {hy:+.3f}, yaw={math.degrees(hyaw):+.1f}°)")
        print(f"Ended at:  map({ex:+.3f}, {ey:+.3f}, yaw={math.degrees(eyaw):+.1f}°)")
        print(f"Return-to-origin accuracy:")
        print(f"  xy error:   {return_xy_err*100:.1f} cm  ({return_xy_err:.3f} m)")
        print(f"  yaw error:  {return_yaw_err:.1f}°")

    print()
    print("Per-leg summary:")
    for label, status, leg_t, _ in results:
        print(f"  {label:<6}  {status:<12}  {leg_t:.1f}s")

    rclpy.shutdown()


if __name__ == "__main__":
    main()
