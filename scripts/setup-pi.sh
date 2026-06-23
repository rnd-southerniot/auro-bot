#!/usr/bin/env bash
# =============================================================================
# setup-pi.sh — Navbot Raspberry Pi 5 bootstrap
# =============================================================================
#
# Idempotent setup script for a fresh Ubuntu 24.04 arm64 server install.
# Installs:
#   - ROS 2 Jazzy (base, not desktop)
#   - Nav2, slam_toolbox, robot_localization
#   - Gazebo Harmonic (via ros_gz vendor packages — no separate osrf apt repo)
#   - Foxglove bridge (web teleop + visualization at studio.foxglove.dev)
#   - Joystick teleop (teleop_twist_joy + joy + gamepad udev rules)
#   - Pico SDK build tools for RP2040 firmware
#   - sllidar_ros2 for RPLIDAR C1
# Configures:
#   - CycloneDDS as the default RMW
#   - udev rules for stable /dev/navbot_rp2040 and /dev/navbot_lidar symlinks
#   - udev rules for Xbox / PlayStation / generic gamepads
#   - User in dialout, i2c, gpio, input groups
#   - I2C-1 bus enabled for IMU and INA238
#   - Optional: static IP via netplan (opt-in: NAVBOT_CONFIGURE_STATIC_IP=1)
#
# Usage:
#   curl -sL <repo>/scripts/setup-pi.sh | bash
#   OR (recommended, after git clone):
#   cd ~/projects/claude-navbot && bash scripts/setup-pi.sh
#
# Optional environment variables (static-IP step — all unset by default):
#   NAVBOT_CONFIGURE_STATIC_IP  Set to 1 to enable the static-IP step.
#                               Unset/empty: step is skipped (safe for re-runs).
#   NAVBOT_STATIC_IP            CIDR form, default 192.168.68.101/24
#   NAVBOT_GATEWAY              Default 192.168.68.1
#   NAVBOT_DNS                  Comma-separated, default 192.168.68.1,1.1.1.1
#   NAVBOT_WIFI_SSID            WiFi SSID. If set together with password,
#                               script configures a wireless interface too.
#   NAVBOT_WIFI_PASSWORD        WiFi WPA/WPA2 password.
#   NAVBOT_NET_IFACE            Force specific ethernet interface name
#                               (else auto-detected from default route).
#
# Requirements:
#   Ubuntu 24.04 arm64 server, fresh install
#   Non-root user with sudo (this script refuses to run as root)
#   Network reachable
#
# Idempotency:
#   All steps are safely re-runnable. A step that has already completed is a no-op.
#
# Exit codes:
#   0   success
#   1   precondition check failed
#   2   apt operation failed
#   3   configuration step failed
#
# =============================================================================

set -euo pipefail

# ---------- Configuration ----------------------------------------------------

readonly REQUIRED_UBUNTU_VERSION="24.04"
readonly REQUIRED_UBUNTU_CODENAME="noble"
readonly REQUIRED_ARCH="arm64"
ROS_DISTRO="jazzy"  # NOT readonly — ROS's setup.bash re-assigns this
readonly RMW_IMPL="rmw_cyclonedds_cpp"
readonly ROS_DOMAIN="0"

# ANSI colours — disabled if not a TTY
if [[ -t 1 ]]; then
    readonly C_GREEN=$'\033[0;32m'
    readonly C_YELLOW=$'\033[0;33m'
    readonly C_RED=$'\033[0;31m'
    readonly C_BLUE=$'\033[0;34m'
    readonly C_RESET=$'\033[0m'
else
    readonly C_GREEN=""
    readonly C_YELLOW=""
    readonly C_RED=""
    readonly C_BLUE=""
    readonly C_RESET=""
fi

# ---------- Logging helpers --------------------------------------------------

log_info()  { echo "${C_BLUE}[INFO]${C_RESET}  $*"; }
log_ok()    { echo "${C_GREEN}[OK]${C_RESET}    $*"; }
log_warn()  { echo "${C_YELLOW}[WARN]${C_RESET}  $*" >&2; }
log_error() { echo "${C_RED}[ERROR]${C_RESET} $*" >&2; }

die() {
    log_error "$*"
    exit "${2:-1}"
}

step_header() {
    echo
    echo "${C_BLUE}═══════════════════════════════════════════════════════════════${C_RESET}"
    echo "${C_BLUE} Step $1: $2${C_RESET}"
    echo "${C_BLUE}═══════════════════════════════════════════════════════════════${C_RESET}"
}

# ---------- Preconditions ----------------------------------------------------

check_preconditions() {
    step_header "0" "Preconditions"

    # Must not be root — we need a regular user for ROS environment
    if [[ $EUID -eq 0 ]]; then
        die "Do not run as root. Run as a regular user with sudo access." 1
    fi

    # Must have sudo
    if ! sudo -n true 2>/dev/null && ! sudo -v; then
        die "This script requires sudo access." 1
    fi

    # Must be Ubuntu 24.04 arm64
    if [[ ! -f /etc/os-release ]]; then
        die "Cannot read /etc/os-release — not a supported system." 1
    fi

    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${VERSION_ID:-}" != "$REQUIRED_UBUNTU_VERSION" ]]; then
        die "This script requires Ubuntu $REQUIRED_UBUNTU_VERSION. Found: ${VERSION_ID:-unknown}" 1
    fi
    if [[ "${VERSION_CODENAME:-}" != "$REQUIRED_UBUNTU_CODENAME" ]]; then
        die "This script requires Ubuntu $REQUIRED_UBUNTU_CODENAME. Found: ${VERSION_CODENAME:-unknown}" 1
    fi

    local arch
    arch=$(dpkg --print-architecture)
    if [[ "$arch" != "$REQUIRED_ARCH" ]]; then
        die "This script requires $REQUIRED_ARCH architecture. Found: $arch" 1
    fi

    # Network reachable
    if ! curl -fsS --max-time 5 http://packages.ros.org/ros2/ubuntu/dists/ > /dev/null; then
        die "Cannot reach packages.ros.org — check network." 1
    fi

    log_ok "Ubuntu $VERSION_ID $VERSION_CODENAME $arch — user: $USER"
    log_ok "sudo available, network reachable"
}

# ---------- Step 1: Locale ---------------------------------------------------

setup_locale() {
    step_header "1" "Locale (UTF-8)"

    if locale | grep -q "LANG=en_US.UTF-8"; then
        log_ok "Locale already en_US.UTF-8"
        return 0
    fi

    sudo apt-get update -qq
    sudo apt-get install -y -qq locales
    sudo locale-gen en_US en_US.UTF-8
    sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
    export LANG=en_US.UTF-8
    log_ok "Locale set to en_US.UTF-8"
}

# ---------- Step 2: ROS 2 apt repository -------------------------------------

setup_ros_repo() {
    step_header "2" "ROS 2 apt repository"

    if [[ -f /etc/apt/sources.list.d/ros2.list ]] && \
       dpkg -l ros-$ROS_DISTRO-ros-base 2>/dev/null | grep -q "^ii"; then
        log_ok "ROS 2 repo already configured and base installed"
        return 0
    fi

    sudo apt-get install -y -qq software-properties-common curl
    sudo add-apt-repository universe -y

    # Install ros-apt-source package for proper key and repo config
    sudo apt-get update -qq
    sudo apt-get install -y -qq curl

    local apt_source_version
    apt_source_version=$(curl -fsSL \
        https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | \
        grep -F "tag_name" | awk -F'"' '{print $4}')

    if [[ -z "$apt_source_version" ]]; then
        die "Failed to fetch ros-apt-source version" 2
    fi

    local deb_url="https://github.com/ros-infrastructure/ros-apt-source/releases/download/${apt_source_version}/ros2-apt-source_${apt_source_version}.${REQUIRED_UBUNTU_CODENAME}_all.deb"

    curl -fsSL -o /tmp/ros2-apt-source.deb "$deb_url"
    sudo dpkg -i /tmp/ros2-apt-source.deb
    rm -f /tmp/ros2-apt-source.deb

    # Workaround for OSUOSL mirror serving wrong cert (2026-04-19).
    # Rewrite ROS apt source from https:// to http://. GPG signature
    # verification remains mandatory via signed-by directive.
    if grep -rql "https://packages.ros.org" /etc/apt/sources.list.d/ 2>/dev/null; then
        sudo sed -i "s|https://packages.ros.org|http://packages.ros.org|g" /etc/apt/sources.list.d/*ros* 2>/dev/null || true
        log_ok "ROS apt source rewritten to http:// (OSUOSL cert workaround)"
    fi

    sudo apt-get update -qq
    log_ok "ROS 2 apt repository configured (version $apt_source_version)"
}

# ---------- Step 3: ROS 2 base + Nav2 + deps ---------------------------------

install_ros2_packages() {
    step_header "3" "ROS 2 Jazzy + Nav2 + Gazebo Harmonic + Foxglove + teleop"

    # Core ROS 2 base — not desktop (no GUI on Pi)
    local packages=(
        # --- ROS 2 base and middleware ---
        ros-$ROS_DISTRO-ros-base
        ros-$ROS_DISTRO-rmw-cyclonedds-cpp

        # --- Navigation and SLAM ---
        ros-$ROS_DISTRO-navigation2
        ros-$ROS_DISTRO-nav2-bringup
        ros-$ROS_DISTRO-nav2-msgs
        ros-$ROS_DISTRO-slam-toolbox
        ros-$ROS_DISTRO-robot-localization

        # --- Robot description and TF ---
        ros-$ROS_DISTRO-robot-state-publisher
        ros-$ROS_DISTRO-xacro
        ros-$ROS_DISTRO-joint-state-publisher
        ros-$ROS_DISTRO-tf2-tools
        ros-$ROS_DISTRO-tf-transformations

        # --- Sensors ---
        # sllidar_ros2 is built from source via Step 11 (navbot.repos)
        # No apt package exists for ros-$ROS_DISTRO-sllidar-ros2
        ros-$ROS_DISTRO-laser-filters

        # --- Teleoperation (three layers: keyboard, joystick, web) ---
        ros-$ROS_DISTRO-teleop-twist-keyboard
        ros-$ROS_DISTRO-teleop-twist-joy
        ros-$ROS_DISTRO-joy
        ros-$ROS_DISTRO-joy-linux
        ros-$ROS_DISTRO-foxglove-bridge

        # --- Simulation: Gazebo Harmonic via ros-gz vendor packages ---
        # This pulls in gz-harmonic (sim, tools, rendering, physics) automatically
        # via the gz_*_vendor packages. No separate osrfoundation apt repo needed.
        ros-$ROS_DISTRO-ros-gz
        ros-$ROS_DISTRO-ros-gz-bridge
        ros-$ROS_DISTRO-ros-gz-sim
        ros-$ROS_DISTRO-ros-gz-image
        ros-$ROS_DISTRO-ros-gz-interfaces

        # --- Nav2 sim integration (navigation demo in Gazebo) ---
        ros-$ROS_DISTRO-nav2-minimal-tb3-sim

        # --- Development tools ---
        ros-dev-tools
        python3-colcon-common-extensions
        python3-rosdep
        python3-vcstool
        python3-pip
        python3-serial
        python3-smbus2

        # --- System tools ---
        git
        build-essential
        cmake
        tmux
        htop
        i2c-tools

        # --- Joystick support at OS level ---
        joystick
        jstest-gtk
    )

    local to_install=()
    for pkg in "${packages[@]}"; do
        if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
            to_install+=("$pkg")
        fi
    done

    if [[ ${#to_install[@]} -eq 0 ]]; then
        log_ok "All packages already installed"
    else
        log_info "Installing ${#to_install[@]} packages (this takes 5-10 min)..."
        sudo apt-get install -y "${to_install[@]}"
        log_ok "Installed ${#to_install[@]} packages"
    fi

    # Initialise rosdep (idempotent)
    if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
        sudo rosdep init
    fi
    rosdep update --rosdistro "$ROS_DISTRO" 2>/dev/null || \
        log_warn "rosdep update had issues — non-fatal"
    log_ok "rosdep initialised"
}

# ---------- Step 4: Firmware build tools (for RP2040) ------------------------

install_firmware_tools() {
    step_header "4" "Firmware build tools (Pico SDK deps)"

    local packages=(
        gcc-arm-none-eabi
        libnewlib-arm-none-eabi
        libstdc++-arm-none-eabi-newlib
        pkg-config
    )

    local to_install=()
    for pkg in "${packages[@]}"; do
        if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
            to_install+=("$pkg")
        fi
    done

    if [[ ${#to_install[@]} -eq 0 ]]; then
        log_ok "Firmware tools already installed"
    else
        sudo apt-get install -y "${to_install[@]}"
        log_ok "Firmware tools installed"
    fi
}

# ---------- Step 5: User groups (dialout, i2c) -------------------------------

setup_user_groups() {
    step_header "5" "User groups (dialout, i2c)"

    local groups_needed=(dialout i2c gpio input)
    local changed=0

    for grp in "${groups_needed[@]}"; do
        if ! getent group "$grp" > /dev/null; then
            sudo groupadd "$grp"
            log_info "Created group: $grp"
        fi
        if ! id -nG "$USER" | grep -qw "$grp"; then
            sudo usermod -aG "$grp" "$USER"
            log_info "Added $USER to group: $grp"
            changed=1
        fi
    done

    if [[ $changed -eq 1 ]]; then
        log_warn "Group changes take effect on next login — run 'newgrp' or re-login"
    else
        log_ok "User $USER already in required groups"
    fi
}

# ---------- Step 6: udev rules for RP2040 and RPLIDAR ------------------------

setup_udev_rules() {
    step_header "6" "udev rules for stable device symlinks"

    local rules_file=/etc/udev/rules.d/99-navbot.rules
    local rules_content='# Navbot udev rules — generated by setup-pi.sh
# Raspberry Pi Pico (RP2040) in CDC-ACM mode
SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="000a", SYMLINK+="navbot_rp2040", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="0005", SYMLINK+="navbot_rp2040", MODE="0666", GROUP="dialout"

# Raspberry Pi Pico in BOOTSEL (mass storage) mode
SUBSYSTEM=="usb", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="0003", MODE="0666", GROUP="dialout"

# RPLIDAR C1 via Silicon Labs CP2102 USB-to-UART
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="navbot_lidar", MODE="0666", GROUP="dialout"

# ST-Link V2 (optional, for STM32 projects)
SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="3748", MODE="0666", GROUP="dialout"

# Joysticks and gamepads — ensure readable by non-root users
# Xbox 360 wired controller
KERNEL=="js[0-9]*", MODE="0666", GROUP="input"
KERNEL=="event[0-9]*", ATTRS{idVendor}=="045e", MODE="0666", GROUP="input"
# Xbox One controller
KERNEL=="event[0-9]*", ATTRS{idVendor}=="045e", ATTRS{idProduct}=="02ea", MODE="0666", GROUP="input"
# PlayStation 4 DualShock
KERNEL=="event[0-9]*", ATTRS{idVendor}=="054c", MODE="0666", GROUP="input"
# Generic HID gamepads
KERNEL=="event[0-9]*", ATTRS{idVendor}=="0079", MODE="0666", GROUP="input"
'

    local needs_update=0
    if [[ ! -f "$rules_file" ]]; then
        needs_update=1
    elif ! diff -q <(echo -n "$rules_content") "$rules_file" >/dev/null 2>&1; then
        needs_update=1
    fi

    if [[ $needs_update -eq 1 ]]; then
        echo "$rules_content" | sudo tee "$rules_file" > /dev/null
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        log_ok "udev rules installed at $rules_file"
        log_info "Symlinks and device rules active:"
        log_info "  /dev/navbot_rp2040  -> RP2040 serial"
        log_info "  /dev/navbot_lidar   -> RPLIDAR C1 serial"
        log_info "  /dev/input/js0      -> joystick (plug in Xbox/PS4 gamepad)"
    else
        log_ok "udev rules already up to date"
    fi
}

# ---------- Step 7: I2C enable (for IMU, INA238) -----------------------------

enable_i2c() {
    step_header "7" "I2C bus (for IMU and INA238)"

    # On Pi 5 with Ubuntu, i2c-1 is typically exposed by default via device tree
    # We just ensure the i2c-dev kernel module loads at boot
    if ! grep -q "^i2c-dev$" /etc/modules 2>/dev/null; then
        echo "i2c-dev" | sudo tee -a /etc/modules > /dev/null
        log_info "Added i2c-dev to /etc/modules (effective after reboot)"
    else
        log_ok "i2c-dev already in /etc/modules"
    fi

    sudo modprobe i2c-dev 2>/dev/null || true

    if [[ -e /dev/i2c-1 ]]; then
        log_ok "/dev/i2c-1 present"
    else
        log_warn "/dev/i2c-1 not present — may require device tree overlay or reboot"
    fi
}

# ---------- Step 8: ROS environment in bashrc -------------------------------

setup_bashrc() {
    step_header "8" "ROS environment in ~/.bashrc"

    local bashrc=$HOME/.bashrc
    local marker="# --- Navbot ROS 2 Jazzy environment ---"

    if grep -qF "$marker" "$bashrc" 2>/dev/null; then
        log_ok "ROS environment already in ~/.bashrc"
        return 0
    fi

    cat >> "$bashrc" <<EOF

$marker
# Managed by scripts/setup-pi.sh — do not edit manually; re-run the script
source /opt/ros/$ROS_DISTRO/setup.bash
export RMW_IMPLEMENTATION=$RMW_IMPL
export ROS_DOMAIN_ID=$ROS_DOMAIN
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET

# Source workspace if present
if [ -f \$HOME/projects/claude-navbot/ros2_ws/install/setup.bash ]; then
    source \$HOME/projects/claude-navbot/ros2_ws/install/setup.bash
fi

# Useful aliases
alias rosnode='ros2 node'
alias rostopic='ros2 topic'
alias rosaction='ros2 action'
alias rosparam='ros2 param'
alias roslaunch='ros2 launch'
alias colcon_build='cd \$HOME/projects/claude-navbot/ros2_ws && colcon build --symlink-install'
# --- End Navbot environment ---
EOF

    log_ok "ROS environment added to ~/.bashrc"
}

# ---------- Step 9: CycloneDDS configuration ---------------------------------

setup_cyclonedds() {
    step_header "9" "CycloneDDS configuration"

    local cyclone_xml=$HOME/.ros/cyclonedds.xml
    mkdir -p "$HOME/.ros"

    if [[ -f "$cyclone_xml" ]]; then
        log_ok "CycloneDDS config already present at $cyclone_xml"
        return 0
    fi

    cat > "$cyclone_xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS xmlns="https://cdds.io/config"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="https://cdds.io/config
            https://raw.githubusercontent.com/eclipse-cyclonedds/cyclonedds/master/etc/cyclonedds.xsd">
    <Domain Id="any">
        <General>
            <Interfaces>
                <!-- Automatically selects the best interface.
                     Override with specific IP if needed. -->
                <NetworkInterface autodetermine="true"/>
            </Interfaces>
            <AllowMulticast>true</AllowMulticast>
            <MaxMessageSize>65500B</MaxMessageSize>
        </General>
        <Internal>
            <SocketReceiveBufferSize min="10MB"/>
        </Internal>
        <Discovery>
            <ParticipantIndex>auto</ParticipantIndex>
        </Discovery>
    </Domain>
</CycloneDDS>
EOF

    # Add URI export to bashrc (if not already there)
    if ! grep -q "CYCLONEDDS_URI" "$HOME/.bashrc"; then
        echo "export CYCLONEDDS_URI=file://$cyclone_xml" >> "$HOME/.bashrc"
    fi

    log_ok "CycloneDDS config created at $cyclone_xml"
}

# ---------- Step 10: Workspace directory -------------------------------------

setup_workspace_dir() {
    step_header "10" "Project directory"

    local dev_dir=$HOME/projects
    if [[ ! -d "$dev_dir" ]]; then
        mkdir -p "$dev_dir"
        log_ok "Created $dev_dir"
    else
        log_ok "$dev_dir already exists"
    fi

    log_info "Next: git clone the navbot repo into $dev_dir"
    log_info "  cd $dev_dir"
    log_info "  git clone -b navbot-experimental https://github.com/rnd-southerniot/claude-navbot.git"
}

# ---------- Step 11: External source dependencies (vcs import) ---------------

install_external_sources() {
    step_header "11" "External source dependencies (sllidar_ros2 and others)"

    local repo_root=$HOME/projects/claude-navbot
    local repos_file=$repo_root/ros2_ws/navbot.repos
    local ws_src=$repo_root/ros2_ws/src

    if [[ ! -f "$repos_file" ]]; then
        log_warn "navbot.repos not found at $repos_file"
        log_warn "Skipping external source install. Clone repo first, then rerun."
        return 0
    fi

    if [[ ! -d "$ws_src" ]]; then
        log_warn "Workspace src directory missing: $ws_src"
        log_warn "Skipping external source install."
        return 0
    fi

    # Import external repos listed in navbot.repos
    # vcs import is idempotent — already-cloned repos are updated, not duplicated
    log_info "Importing external sources via vcs..."
    if command -v vcs >/dev/null 2>&1; then
        cd "$ws_src" && vcs import < "$repos_file" || {
            log_warn "vcs import had warnings — check output above"
        }
        log_ok "External sources imported into $ws_src"
    else
        log_error "vcs tool not found — install python3-vcstool first"
        return 1
    fi

    # Pull rosdep dependencies for everything in src/
    log_info "Installing rosdep dependencies for workspace..."
    # ROS 2 setup.bash reads unbound vars (e.g. AMENT_TRACE_SETUP_FILES).
    # Temporarily disable -u to avoid 'unbound variable' crashes.
    set +u
    source /opt/ros/$ROS_DISTRO/setup.bash
    set -u
    cd "$repo_root/ros2_ws" && \
        rosdep install --from-paths src --ignore-src -r -y 2>&1 | \
        tail -20 || log_warn "rosdep reported issues — review above"

    log_ok "External sources ready. User must run 'colcon build' next."
}

# ---------- Step 11.5: Kernel network tuning (CycloneDDS) --------------------

configure_kernel_tuning() {
    log_info "Configuring kernel network buffers for CycloneDDS..."

    local sysctl_conf="/etc/sysctl.d/10-cyclonedds.conf"

    if [[ -f "$sysctl_conf" ]] && grep -q "net.core.rmem_max=16777216" "$sysctl_conf"; then
        log_info "  sysctl config already in place — skipping"
        return 0
    fi

    sudo tee "$sysctl_conf" > /dev/null <<'EOF'
# CycloneDDS requires >=10MB socket buffers per ~/.ros/cyclonedds.xml
# Ubuntu 24.04 default net.core.rmem_max is 208KB which causes every
# ROS 2 node to abort at rmw_create_node() with:
#   failed to increase socket receive buffer size to at least 10485760
# Setting 16MB gives 6MB headroom over the DDS minimum.
# See: https://docs.ros.org/en/jazzy/How-To-Guides/DDS-tuning.html
net.core.rmem_max=16777216
net.core.rmem_default=16777216
net.core.wmem_max=16777216
net.core.wmem_default=16777216
EOF

    sudo sysctl -p "$sysctl_conf" > /dev/null

    # Verify applied
    local rmem_max
    rmem_max=$(sysctl -n net.core.rmem_max)
    if [[ "$rmem_max" != "16777216" ]]; then
        log_error "  sysctl apply failed: rmem_max=$rmem_max (expected 16777216)"
        return 1
    fi

    log_info "  kernel buffers: rmem_max=16MB, wmem_max=16MB applied"
}

# ---------- Step 11.6: Optional static IP via netplan ------------------------
#
# Opt-in via NAVBOT_CONFIGURE_STATIC_IP=1. When opted in, writes
# /etc/netplan/99-navbot-static.yaml and disables cloud-init network
# regeneration. All other parameters default to values validated on the
# navbot lab Pi (192.168.68.101 on the 192.168.68.0/24 subnet).
#
# ROLLBACK (SSH still possible):
#   sudo rm /etc/netplan/99-navbot-static.yaml
#   sudo rm /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
#   sudo netplan apply
#
# ROLLBACK (SSH lost — needs physical console):
#   Same commands, via attached keyboard/monitor.
#
configure_static_ip() {
    if [[ "${NAVBOT_CONFIGURE_STATIC_IP:-}" != "1" ]]; then
        step_header "11.6" "Static IP (skipped — NAVBOT_CONFIGURE_STATIC_IP not set)"
        log_info "Re-run with NAVBOT_CONFIGURE_STATIC_IP=1 to configure static IP"
        return 0
    fi

    step_header "11.6" "Static IP via netplan"

    local static_ip="${NAVBOT_STATIC_IP:-192.168.68.101/24}"
    local gateway="${NAVBOT_GATEWAY:-192.168.68.1}"
    local dns_csv="${NAVBOT_DNS:-192.168.68.1,1.1.1.1}"
    local wifi_ssid="${NAVBOT_WIFI_SSID:-}"
    local wifi_pass="${NAVBOT_WIFI_PASSWORD:-}"
    local forced_iface="${NAVBOT_NET_IFACE:-}"

    # Detect primary interface from current default route
    local iface
    if [[ -n "$forced_iface" ]]; then
        iface="$forced_iface"
    else
        iface=$(ip -4 route show default 2>/dev/null | awk '/default/ {print $5; exit}')
    fi
    if [[ -z "$iface" ]]; then
        log_error "Cannot detect default-route interface. Set NAVBOT_NET_IFACE=ethX."
        return 3
    fi
    log_info "Target interface: $iface"
    log_info "Target static IP: $static_ip  gateway: $gateway  dns: $dns_csv"

    # Convert DNS CSV to space-padded comma list for YAML
    local dns_yaml
    dns_yaml=$(echo "$dns_csv" | awk -F, '{for(i=1;i<=NF;i++){printf "%s%s",(i>1?", ":""),$i}}')

    # Build target netplan YAML
    local netplan_file="/etc/netplan/99-navbot-static.yaml"
    local tmp_yaml
    tmp_yaml=$(mktemp)

    {
        echo "# Managed by scripts/setup-pi.sh — do not edit manually"
        echo "# Rollback: sudo rm ${netplan_file} && sudo netplan apply"
        echo "network:"
        echo "  version: 2"
        echo "  ethernets:"
        echo "    ${iface}:"
        echo "      dhcp4: no"
        echo "      addresses: [${static_ip}]"
        echo "      routes:"
        echo "        - to: default"
        echo "          via: ${gateway}"
        echo "      nameservers:"
        echo "        addresses: [${dns_yaml}]"
        if [[ -n "$wifi_ssid" && -n "$wifi_pass" ]]; then
            local wifi_iface
            wifi_iface=$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')
            if [[ -n "$wifi_iface" ]]; then
                echo "  wifis:"
                echo "    ${wifi_iface}:"
                echo "      dhcp4: no"
                echo "      addresses: [${static_ip}]"
                echo "      access-points:"
                echo "        \"${wifi_ssid}\":"
                echo "          password: \"${wifi_pass}\""
                echo "      routes:"
                echo "        - to: default"
                echo "          via: ${gateway}"
                echo "      nameservers:"
                echo "        addresses: [${dns_yaml}]"
            else
                log_warn "WiFi env vars set but no wireless interface detected — skipping WiFi stanza"
            fi
        fi
    } > "$tmp_yaml"

    # Idempotency: skip if target file already matches
    if [[ -f "$netplan_file" ]] && diff -q "$tmp_yaml" "$netplan_file" >/dev/null 2>&1; then
        log_ok "Netplan config already matches target — skipping"
        rm -f "$tmp_yaml"
    else
        sudo cp "$tmp_yaml" "$netplan_file"
        sudo chmod 600 "$netplan_file"
        rm -f "$tmp_yaml"
        log_ok "Wrote $netplan_file"

        # Use `netplan try` when running interactively so a mistake auto-
        # rolls-back after 120s. Non-interactive runs fall back to apply
        # with an explicit warning.
        if [[ -t 0 ]]; then
            log_info "Running 'sudo netplan try' (120s rollback timer — press ENTER to accept)"
            sudo netplan try --timeout 120 || {
                log_error "netplan try rejected or timed out — config rolled back"
                return 3
            }
        else
            log_warn "Non-interactive shell — running 'netplan apply' without rollback timer"
            log_warn "If SSH hangs, the new config is active and you must console in to fix"
            sudo netplan apply
        fi
        log_ok "Netplan applied"
    fi

    # Disable cloud-init network regeneration
    local cloud_cfg="/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg"
    if [[ -f "$cloud_cfg" ]] && grep -q 'config: disabled' "$cloud_cfg" 2>/dev/null; then
        log_ok "cloud-init network regen already disabled"
    else
        echo 'network: {config: disabled}' | sudo tee "$cloud_cfg" > /dev/null
        log_ok "Disabled cloud-init network regeneration at $cloud_cfg"
    fi
}

# ---------- Step 12: Summary -------------------------------------------------

print_summary() {
    step_header "DONE" "Summary"

    cat <<EOF

${C_GREEN}System setup complete.${C_RESET}

Installed:
  - Ubuntu $REQUIRED_UBUNTU_VERSION arm64 (pre-existing)
  - ROS 2 $ROS_DISTRO base
  - Navigation:  Nav2, slam_toolbox, robot_localization
  - Sensors:     sllidar_ros2 for RPLIDAR C1
  - Simulation:  Gazebo Harmonic via ros_gz vendor packages
  - Teleop:      keyboard, joystick (teleop_twist_joy + joy-linux)
  - Web UI:      foxglove_bridge (connect from studio.foxglove.dev)
  - Firmware:    Pico SDK build tools (arm-none-eabi-gcc)
  - Middleware:  CycloneDDS (default)

Configured:
  - User $USER in groups: dialout, i2c, gpio
  - udev rules for RP2040 and RPLIDAR C1
  - I2C bus enabled
  - ROS environment in ~/.bashrc
  - ROS_DOMAIN_ID=$ROS_DOMAIN
  - RMW_IMPLEMENTATION=$RMW_IMPL

${C_YELLOW}Next steps:${C_RESET}

1. Log out and back in (or run 'newgrp dialout') for group changes to take effect

2. Clone the repo:
   cd ~/projects
   git clone -b navbot-experimental https://github.com/rnd-southerniot/claude-navbot.git
   cd claude-navbot

3. External sources already imported and rosdep resolved by setup-pi.sh
   (Step 11). Proceed directly to colcon build.

4. Build the workspace:
   colcon build --symlink-install
   source install/setup.bash

5. Flash RP2040 firmware (use the known-good UF2 from the repo):
   # Put RP2040 in BOOTSEL mode (hold BOOTSEL while plugging USB)
   cp ~/projects/claude-navbot/firmware/makerpi_rp2040_base/firmware_v1.2.0.uf2 \\
     /media/$USER/RPI-RP2/

6. Run diagnostics:
   bash scripts/diagnostics.sh

${C_BLUE}Teleop quick reference:${C_RESET}

  Keyboard:
    ros2 run teleop_twist_keyboard teleop_twist_keyboard

  Joystick (Xbox or similar, plugged in via USB):
    ros2 launch teleop_twist_joy teleop-launch.py joy_config:=xbox

  Web/Mobile (after launching the robot stack):
    On Pi:    ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765
    On phone: open https://studio.foxglove.dev
              connect to ws://<pi-ip>:8765

${C_BLUE}Simulation quick reference:${C_RESET}

  Test Gazebo itself:
    gz sim empty.sdf

  Run the Nav2 demo in sim (no navbot_gazebo package required):
    ros2 launch nav2_bringup tb3_simulation_launch.py

  Run the navbot sim (once navbot_gazebo package exists):
    ros2 launch navbot_gazebo sim.launch.py

${C_YELLOW}Reboot recommended${C_RESET} to ensure all group and module changes are active:
   sudo reboot
EOF
}

# ---------- Main -------------------------------------------------------------

main() {
    echo
    echo "${C_BLUE}╔═══════════════════════════════════════════════════════════════╗${C_RESET}"
    echo "${C_BLUE}║           Navbot Raspberry Pi 5 Bootstrap Script              ║${C_RESET}"
    echo "${C_BLUE}║     Ubuntu 24.04 → ROS 2 Jazzy + Nav2 + Gazebo + Foxglove     ║${C_RESET}"
    echo "${C_BLUE}╚═══════════════════════════════════════════════════════════════╝${C_RESET}"

    check_preconditions
    setup_locale
    setup_ros_repo
    install_ros2_packages
    install_firmware_tools
    setup_user_groups
    setup_udev_rules
    enable_i2c
    setup_bashrc
    setup_cyclonedds
    setup_workspace_dir
    install_external_sources
    configure_kernel_tuning || { log_error "kernel tuning failed"; exit 1; }
    configure_static_ip    || { log_error "static-ip step failed"; exit 1; }
    print_summary

    exit 0
}

main "$@"
