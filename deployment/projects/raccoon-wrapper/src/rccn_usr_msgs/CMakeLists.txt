cmake_minimum_required(VERSION 3.8)
project(rccn_usr_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(action_msgs REQUIRED)

set(message_files
  "msg/RawBytes.msg"
)

set(action_files
  "action/StressTest.action"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${action_files}
  ${message_files}
  DEPENDENCIES action_msgs
)

ament_export_dependencies(rosidl_default_runtime)

ament_package()