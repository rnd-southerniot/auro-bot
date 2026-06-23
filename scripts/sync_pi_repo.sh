#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${NAVBOT_SYNC_BRANCH:-main}"
MODE="ff-only"
BUILD=0

usage() {
  cat <<EOF
Usage: $0 [--hard] [--build]

Synchronize this working copy with origin/${BRANCH}.

  --hard   discard local source changes and untracked source files
  --build  rebuild ros2_ws after syncing

Ignored runtime outputs such as captures/, ros2_ws/build/, ros2_ws/install/,
and ros2_ws/log/ are not removed.
EOF
}

while (($# > 0)); do
  case "$1" in
    --hard)
      MODE="hard"
      ;;
    --build)
      BUILD=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

cd "${ROOT_DIR}"

git fetch --all --prune

current_branch="$(git branch --show-current)"
if [[ "${current_branch}" != "${BRANCH}" ]]; then
  echo "Expected branch ${BRANCH}, currently on ${current_branch}" >&2
  exit 1
fi

if [[ "${MODE}" == "hard" ]]; then
  git reset --hard "origin/${BRANCH}"
  git clean -fd
else
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Working tree is dirty; rerun with --hard to discard source drift." >&2
    git status --short
    exit 1
  fi
  git pull --ff-only origin "${BRANCH}"
fi

git status --short --branch

if ((BUILD)); then
  "${ROOT_DIR}/scripts/build_ros2_ws.sh"
fi
