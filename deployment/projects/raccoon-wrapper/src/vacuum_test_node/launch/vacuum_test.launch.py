from launch import LaunchDescription
from launch_ros.actions import Node

def node_by_name(name: str):
    return Node(
        package=name,
        executable=name,
        name=name,
        output='screen',
        emulate_tty=True,
    )

def generate_launch_description():
    return LaunchDescription([
        node_by_name("thermal_test_controller"),
        node_by_name("rccn_usr_comm"),
        node_by_name("vacuum_test_node")
    ])