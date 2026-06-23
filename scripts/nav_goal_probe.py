#!/usr/bin/env python3
"""
Send a navigate_to_pose goal and capture /cmd_vel_nav stats during execution.
Usage:  nav_goal_probe.py <dx> <dy> <dyaw_rad> [timeout_s]
dx, dy, dyaw are in the robot's CURRENT body frame (forward = +x).
"""
import math
import statistics
import sys
import time
from threading import Event

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.duration import Duration

from geometry_msgs.msg import Twist, PoseStamped, TransformStamped
from nav2_msgs.action import NavigateToPose
from tf2_ros import Buffer, TransformListener


def yaw_from_quat(qx, qy, qz, qw):
    return math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


class Probe(Node):
    def __init__(self):
        super().__init__('nav_goal_probe')
        self.tf_buf = Buffer()
        self.tf_listen = TransformListener(self.tf_buf, self)
        self.cmd_vel_samples = []
        self.create_subscription(Twist, '/cmd_vel_nav', self._on_cmd_nav, 50)
        self.nav_client = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        self.done_evt = Event()
        self.result = None

    def _on_cmd_nav(self, msg: Twist):
        self.cmd_vel_samples.append((time.time(), msg.linear.x, msg.angular.z))

    def get_pose(self, frame='map') -> TransformStamped | None:
        deadline = time.time() + 4.0
        while time.time() < deadline:
            try:
                return self.tf_buf.lookup_transform(frame, 'base_footprint',
                                                   rclpy.time.Time())
            except Exception:
                rclpy.spin_once(self, timeout_sec=0.2)
        return None

    def send_goal(self, x_map, y_map, yaw_map, timeout_s=30.0,
                  log_trajectory=False):
        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            print('ERROR: nav action server unavailable')
            return False
        goal = NavigateToPose.Goal()
        p = goal.pose
        p.header.frame_id = 'map'
        p.header.stamp = self.get_clock().now().to_msg()
        p.pose.position.x = float(x_map)
        p.pose.position.y = float(y_map)
        p.pose.orientation.z = math.sin(yaw_map / 2.0)
        p.pose.orientation.w = math.cos(yaw_map / 2.0)
        print(f'goal -> map({x_map:+.3f}, {y_map:+.3f}, yaw={math.degrees(yaw_map):+.1f}°)')
        send = self.nav_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, send, timeout_sec=5.0)
        gh = send.result()
        if gh is None or not gh.accepted:
            print('ERROR: goal rejected')
            return False
        print('goal accepted; executing...')
        result_future = gh.get_result_async()
        trajectory = []
        t0 = time.time()
        last_log = 0.0
        while not result_future.done() and (time.time() - t0) < timeout_s:
            rclpy.spin_once(self, timeout_sec=0.1)
            if log_trajectory and (time.time() - last_log) >= 0.3:
                try:
                    tf = self.tf_buf.lookup_transform('map', 'base_footprint',
                                                     rclpy.time.Time())
                    q = tf.transform.rotation
                    yaw = yaw_from_quat(q.x, q.y, q.z, q.w)
                    trajectory.append((time.time() - t0,
                                       tf.transform.translation.x,
                                       tf.transform.translation.y,
                                       yaw))
                    last_log = time.time()
                except Exception:
                    pass
        if not result_future.done():
            print(f'TIMEOUT after {timeout_s:.0f}s; cancelling')
            cancel = gh.cancel_goal_async()
            rclpy.spin_until_future_complete(self, cancel, timeout_sec=2.0)
            return False
        self.result = result_future.result()
        if log_trajectory and trajectory:
            print('trajectory (t, x, y, yaw°):')
            for t, x, y, yaw in trajectory:
                print(f'  t={t:5.2f}s  ({x:+.3f}, {y:+.3f})  yaw={math.degrees(yaw):+6.1f}°')
        return True


def summarise(samples):
    if not samples:
        return 'no cmd_vel samples received'
    lin = [s[1] for s in samples]
    ang = [s[2] for s in samples]
    return (f'count={len(samples)}  '
            f'lin.x: min={min(lin):+.4f} max={max(lin):+.4f} '
            f'mean={statistics.mean(lin):+.4f} '
            f'|>0.01|={sum(1 for v in lin if abs(v) > 0.01)}  '
            f'ang.z: min={min(ang):+.4f} max={max(ang):+.4f} '
            f'mean={statistics.mean(ang):+.4f}')


def main():
    if len(sys.argv) < 4:
        print('usage: nav_goal_probe.py <dx> <dy> <dyaw_rad> [timeout_s]')
        sys.exit(2)
    dx = float(sys.argv[1])
    dy = float(sys.argv[2])
    dyaw = float(sys.argv[3])
    timeout_s = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0

    rclpy.init()
    node = Probe()

    # Wait for TF to settle
    time.sleep(2.0)
    tf0 = node.get_pose('map')
    if tf0 is None:
        print('ERROR: no map->base_footprint transform')
        rclpy.shutdown()
        sys.exit(3)
    x0 = tf0.transform.translation.x
    y0 = tf0.transform.translation.y
    q = tf0.transform.rotation
    yaw0 = yaw_from_quat(q.x, q.y, q.z, q.w)
    print(f'start pose: map({x0:+.3f}, {y0:+.3f}, yaw={math.degrees(yaw0):+.1f}°)')

    # Transform body-frame delta into map frame
    cy, sy = math.cos(yaw0), math.sin(yaw0)
    x_g = x0 + cy * dx - sy * dy
    y_g = y0 + sy * dx + cy * dy
    yaw_g = yaw0 + dyaw

    log_traj = '--traj' in sys.argv
    ok = node.send_goal(x_g, y_g, yaw_g, timeout_s=timeout_s,
                        log_trajectory=log_traj)

    tf1 = node.get_pose('map')
    if tf1 is not None:
        x1 = tf1.transform.translation.x
        y1 = tf1.transform.translation.y
        q = tf1.transform.rotation
        yaw1 = yaw_from_quat(q.x, q.y, q.z, q.w)
        travel = math.hypot(x1 - x0, y1 - y0)
        rot = math.degrees(yaw1 - yaw0)
        print(f'end pose:   map({x1:+.3f}, {y1:+.3f}, yaw={math.degrees(yaw1):+.1f}°)')
        print(f'delta: travel={travel:.3f} m, rotation={rot:+.1f}°')
    print(f'cmd_vel_nav: {summarise(node.cmd_vel_samples)}')
    if ok and node.result is not None:
        status = node.result.status
        print(f'nav result status: {status}')
    rclpy.shutdown()


if __name__ == '__main__':
    main()
