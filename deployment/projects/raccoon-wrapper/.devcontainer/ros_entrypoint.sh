#!/bin/bash
# shellcheck disable=SC1090,SC1091
set -e

# setup ros2 environment
source /opt/ros/"$ROS_DISTRO"/setup.bash --
source ~/ros2_ws/install/setup.bash --

# source rust
source ~/.cargo/env

exec "$@"
