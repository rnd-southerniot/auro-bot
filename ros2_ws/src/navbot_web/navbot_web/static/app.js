const stateEls = {
  rosStatus: document.getElementById("ros-status"),
  baseStatus: document.getElementById("base-status"),
  scanStatus: document.getElementById("scan-status"),
  controllerState: document.getElementById("controller-state"),
  estopState: document.getElementById("estop-state"),
  odomX: document.getElementById("odom-x"),
  odomY: document.getElementById("odom-y"),
  odomYaw: document.getElementById("odom-yaw"),
  odomLinear: document.getElementById("odom-linear"),
  odomAngular: document.getElementById("odom-angular"),
  odomAge: document.getElementById("odom-age"),
  scanFrame: document.getElementById("scan-frame"),
  scanBeams: document.getElementById("scan-beams"),
  scanAge: document.getElementById("scan-age"),
  jointAge: document.getElementById("joint-age"),
  powerStatus: document.getElementById("power-status"),
  powerAge: document.getElementById("power-age"),
  powerBusVoltage: document.getElementById("power-bus-voltage"),
  powerCurrent: document.getElementById("power-current"),
  powerPower: document.getElementById("power-power"),
  powerShuntVoltage: document.getElementById("power-shunt-voltage"),
  powerTemperature: document.getElementById("power-temperature"),
  powerMessage: document.getElementById("power-message"),
  imuStatus: document.getElementById("imu-status"),
  imuAge: document.getElementById("imu-age"),
  imuHeading: document.getElementById("imu-heading"),
  imuYaw: document.getElementById("imu-yaw"),
  imuPitch: document.getElementById("imu-pitch"),
  imuRoll: document.getElementById("imu-roll"),
  imuVariant: document.getElementById("imu-variant"),
  imuFrame: document.getElementById("imu-frame"),
  imuGyroAddress: document.getElementById("imu-gyro-address"),
  imuAccelAddress: document.getElementById("imu-accel-address"),
  imuMagAddress: document.getElementById("imu-mag-address"),
  imuMessage: document.getElementById("imu-message"),
  batMotorVoltage: document.getElementById("bat-motor-voltage"),
  batLidarVoltage: document.getElementById("bat-lidar-voltage"),
  batAge: document.getElementById("bat-age"),
  captureActive: document.getElementById("capture-active"),
  captureFolder: document.getElementById("capture-folder"),
  captureError: document.getElementById("capture-error"),
  captureList: document.getElementById("capture-list"),
};

const linearSpeed = document.getElementById("linear-speed");
const angularSpeed = document.getElementById("angular-speed");
const linearSpeedValue = document.getElementById("linear-speed-value");
const angularSpeedValue = document.getElementById("angular-speed-value");
const captureLabel = document.getElementById("capture-label");

let driveTimer = null;
let activeDriveKey = null;

function fmtAge(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${value.toFixed(2)} s`;
}

function fmtMaybeNumber(value, digits, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function fmtHexAddress(value) {
  if (value === null || value === undefined || Number(value) <= 0) {
    return "-";
  }
  return `0x${Number(value).toString(16).toUpperCase()}`;
}

async function postJson(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true,
  });
  return response.json();
}

function updateSliderText() {
  linearSpeedValue.textContent = `${Number(linearSpeed.value).toFixed(2)} m/s`;
  angularSpeedValue.textContent = `${Number(angularSpeed.value).toFixed(2)} rad/s`;
}

function currentLinear(baseValue) {
  return Number(baseValue) * Number(linearSpeed.value);
}

function currentAngular(baseValue) {
  return Number(baseValue) * Number(angularSpeed.value);
}

function stopDrive() {
  if (driveTimer !== null) {
    clearInterval(driveTimer);
    driveTimer = null;
  }
  activeDriveKey = null;
  postJson("/api/stop").catch(() => {});
}

function startDrive(linear, angular, key = null) {
  if (key && activeDriveKey === key) {
    return;
  }
  stopDrive();
  activeDriveKey = key;
  const payload = { linear, angular };
  postJson("/api/cmd_vel", payload).catch(() => {});
  driveTimer = setInterval(() => {
    postJson("/api/cmd_vel", payload).catch(() => {});
  }, 100);
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const state = await response.json();

    stateEls.rosStatus.textContent = state.ros_bridge_alive ? "Alive" : "Down";
    stateEls.baseStatus.textContent = state.base_bridge_alive ? "Alive" : "Stale";
    stateEls.scanStatus.textContent = state.scan.alive ? "Alive" : "Stale";
    stateEls.controllerState.textContent = state.controller.state || "UNKNOWN";
    stateEls.estopState.textContent = state.estop.active ? "ACTIVE" : "Clear";

    stateEls.odomX.textContent = state.odom.x.toFixed(3);
    stateEls.odomY.textContent = state.odom.y.toFixed(3);
    stateEls.odomYaw.textContent = state.odom.yaw.toFixed(3);
    stateEls.odomLinear.textContent = state.odom.linear_x.toFixed(3);
    stateEls.odomAngular.textContent = state.odom.angular_z.toFixed(3);
    stateEls.odomAge.textContent = fmtAge(state.odom.age_sec);

    stateEls.scanFrame.textContent = state.scan.frame_id || "-";
    stateEls.scanBeams.textContent = String(state.scan.beam_count || 0);
    stateEls.scanAge.textContent = fmtAge(state.scan.age_sec);
    stateEls.jointAge.textContent = fmtAge(state.joint_states.age_sec);
    stateEls.powerStatus.textContent = state.power.alive
      ? (state.power.available ? "Live" : "Error")
      : "Stale";
    stateEls.powerAge.textContent = fmtAge(state.power.age_sec);
    stateEls.powerBusVoltage.textContent = fmtMaybeNumber(state.power.bus_voltage_v, 3, " V");
    stateEls.powerCurrent.textContent = fmtMaybeNumber(state.power.current_a, 3, " A");
    stateEls.powerPower.textContent = fmtMaybeNumber(state.power.power_w, 3, " W");
    stateEls.powerShuntVoltage.textContent = fmtMaybeNumber(state.power.shunt_voltage_v, 4, " V");
    stateEls.powerTemperature.textContent = fmtMaybeNumber(state.power.temperature_c, 2, " C");
    stateEls.powerMessage.textContent = state.power.message || "-";

    if (state.batteries) {
      stateEls.batMotorVoltage.textContent = fmtMaybeNumber(state.batteries.motor_voltage, 3, " V");
      stateEls.batLidarVoltage.textContent = fmtMaybeNumber(state.batteries.lidar_voltage, 3, " V");
      stateEls.batAge.textContent = fmtAge(state.batteries.age_sec);
    }

    stateEls.imuStatus.textContent = state.imu.alive
      ? (state.imu.available ? "Live" : "Error")
      : "Stale";
    stateEls.imuAge.textContent = fmtAge(state.imu.age_sec);
    stateEls.imuHeading.textContent = fmtMaybeNumber(state.imu.heading_deg, 1, " deg");
    stateEls.imuYaw.textContent = fmtMaybeNumber(state.imu.yaw_rad, 3, " rad");
    stateEls.imuPitch.textContent = fmtMaybeNumber(state.imu.pitch_rad, 3, " rad");
    stateEls.imuRoll.textContent = fmtMaybeNumber(state.imu.roll_rad, 3, " rad");
    stateEls.imuVariant.textContent = state.imu.variant || "-";
    stateEls.imuFrame.textContent = state.imu.frame_id || "-";
    stateEls.imuGyroAddress.textContent = fmtHexAddress(state.imu.gyro_address);
    stateEls.imuAccelAddress.textContent = fmtHexAddress(state.imu.accel_address);
    stateEls.imuMagAddress.textContent = fmtHexAddress(state.imu.mag_address);
    stateEls.imuMessage.textContent = state.imu.message || "-";

    stateEls.captureActive.textContent = state.capture.active ? "Yes" : "No";
    stateEls.captureFolder.textContent = state.capture.folder || "-";
    stateEls.captureError.textContent = state.capture.last_error || "-";

    stateEls.captureList.innerHTML = "";
    state.capture.recent.forEach((capture) => {
      const item = document.createElement("li");
      item.textContent = `${capture.folder} (${capture.label || "capture"})`;
      stateEls.captureList.appendChild(item);
    });
  } catch (_error) {
    stateEls.rosStatus.textContent = "Disconnected";
    stateEls.baseStatus.textContent = "Unknown";
    stateEls.scanStatus.textContent = "Unknown";
  }
}

document.querySelectorAll(".drive").forEach((button) => {
  const baseLinear = Number(button.dataset.linear || 0);
  const baseAngular = Number(button.dataset.angular || 0);
  const handlePress = (event) => {
    event.preventDefault();
    startDrive(currentLinear(baseLinear), currentAngular(baseAngular));
  };
  button.addEventListener("pointerdown", handlePress);
  button.addEventListener("pointerup", stopDrive);
  button.addEventListener("pointercancel", stopDrive);
  button.addEventListener("pointerleave", stopDrive);
});

document.getElementById("stop-button").addEventListener("click", stopDrive);
document.getElementById("capture-start").addEventListener("click", async () => {
  await postJson("/api/capture/start", { label: captureLabel.value });
  refreshStatus();
});
document.getElementById("capture-stop").addEventListener("click", async () => {
  await postJson("/api/capture/stop");
  refreshStatus();
});

linearSpeed.addEventListener("input", updateSliderText);
angularSpeed.addEventListener("input", updateSliderText);

window.addEventListener("keydown", (event) => {
  if (event.repeat) {
    return;
  }
  const key = event.key.toLowerCase();
  if (key === "w" || event.key === "ArrowUp") {
    startDrive(currentLinear(1), 0, "forward");
  } else if (key === "s" || event.key === "ArrowDown") {
    startDrive(currentLinear(-1), 0, "backward");
  } else if (key === "a" || event.key === "ArrowLeft") {
    startDrive(0, currentAngular(1), "left");
  } else if (key === "d" || event.key === "ArrowRight") {
    startDrive(0, currentAngular(-1), "right");
  } else if (event.code === "Space") {
    stopDrive();
  }
});

window.addEventListener("keyup", stopDrive);
window.addEventListener("beforeunload", stopDrive);

updateSliderText();
refreshStatus();
setInterval(refreshStatus, 250);
