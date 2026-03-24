#!/bin/bash

set -ex

# First, compile interface packages for x86


export PWD="$(pwd)"

source /opt/ros/humble/setup.bash
colcon build \
    --merge-install \
    --build-base "$PWD/build/host" \
    --install-base "$PWD/install/host" \
    --packages-up-to thermal_test_msgs rccn_usr_msgs 

# Now cross compile the interface packages
unset LD_LIBRARY_PATH
source /opt/raccoon/0.4/environment-setup-cortexa53-crypto-poky-linux

export ROS_DISTRO=${ROS_DISTRO:-humble}
export ROS_VERSION=2
export ROS_PYTHON_VERSION=3
export PYTHONPATH=$OECORE_NATIVE_SYSROOT/usr/lib/python3.12/site-packages:$OECORE_TARGET_SYSROOT/usr/opt/ros/$ROS_DISTRO/lib/python3.12/site-packages
export AMENT_PREFIX_PATH="$OECORE_TARGET_SYSROOT/usr/opt/ros/$ROS_DISTRO:$OECORE_TARGET_SYSROOT/usr/opt/ros/$ROS_DISTRO/share:$OECORE_TARGET_SYSROOT/usr/opt/ros/$ROS_DISTRO/lib/cmake:$AMENT_PREFIX_PATH"
export AMENT_PREFIX_PATH="/opt/raccoon/0.4/sysroots/x86_64-pokysdk-linux/usr/opt/ros/humble/:$AMENT_PREFIX_PATH"

## Architecture-specific args
## Not sure why we have to pass this, but we get the following error otherwise:
##    Generate bindings in '/home/rosdev/ros2_ws/target/debug/build/r2r_msg_gen-x/out/y'
##    /opt/raccoon/0.4/sysroots/cortexa53-crypto-poky-linux/usr/include/bits/timesize.h:23:10: fatal error: 'bits/timesize-32.h' file not found
export ARCH_FLAGS="-D__WORDSIZE=64 -D__LP64__=1 -D__aarch64__"
export BINDGEN_EXTRA_CLANG_ARGS="--sysroot=$OECORE_TARGET_SYSROOT $ARCH_FLAGS"

export LD_LIBRARY_PATH="$PWD/install/host/lib:/opt/raccoon/0.4/sysroots/x86_64-pokysdk-linux/usr/opt/ros/humble/lib:$LD_LIBRARY_PATH"
export LD_LIBRARY_PATH="$PWD/install/target/lib:$OECORE_TARGET_SYSROOT/usr/opt/ros/humble/lib:$LD_LIBRARY_PATH"
#export LD_LIBRARY_PATH="$OECORE_NATIVE_SYSROOT/usr/lib:$LD_LIBRARY_PATH"
export AMENT_PREFIX_PATH="$PWD/install/host:$AMENT_PREFIX_PATH"
export AMENT_PREFIX_PATH="$PWD/install/target:$AMENT_PREFIX_PATH"
export AMENT_PREFIX_PATH="$OECORE_TARGET_SYSROOT/usr/opt/ros/$ROS_DISTRO:$AMENT_PREFIX_PATH"
#export PATH="/opt/raccoon/0.4/sysroots/x86_64-pokysdk-linux/bin/:$PATH"


export PYTHON_SOABI="cpython-312-aarch64-linux-gnu"


cat >/tmp/ld-wrapper <<EOF
#!/bin/sh
$CC -Wl,-rpath-link=$OECORE_TARGET_SYSROOT/usr/opt/ros/humble/lib "\$@"
EOF
chmod +x /tmp/ld-wrapper
export CARGO_TARGET_AARCH64_POKY_LINUX_GNU_LINKER="/tmp/ld-wrapper"

cat >/tmp/cargo <<EOF
#!/bin/sh
echo "hello from the realest of cargos"
cargo.real "\$@"
EOF
chmod +x /tmp/cargo
export PATH="/tmp:$PATH"

export IDL_PACKAGE_FILTER="std_msgs;rccn_usr_msgs;thermal_test_msgs"

# Cross-compile workspace
colcon build \
    --merge-install \
    --build-base "$PWD/build/target" \
    --install-base "$PWD/install/target" \
    --cmake-args \
        " -DCMAKE_TOOLCHAIN_FILE=$CMAKE_TOOLCHAIN_FILE" \
        " -DCMAKE_STAGING_PREFIX=$PWD/install/target" \
        " -DBUILD_TESTING=OFF" \
        " -DPython3_NumPy_INCLUDE_DIR=$OECORE_TARGET_SYSROOT/usr/lib/python3.12/site-packages/numpy/core/include" \
        " -DPYTHON_SOABI=$PYTHON_SOABI" \
        " $ARCH_FLAGS" \
    --event-handlers console_direct+ \
    --rust-target aarch64-poky-linux-gnu \
    --cargo-args \
        " --release" \
    --packages-up-to vacuum_test_node thermal_test_controller rccn_usr_comm 

exit 0

cargo.real build \
    --locked

mkdir -p $PWD/install/target/lib/rccn_usr_example_app
cp \
    $PWD/target/aarch64-poky-linux-gnu/debug/rccn_usr_example_app \
    $PWD/install/target/lib/rccn_usr_example_app

exit 0

