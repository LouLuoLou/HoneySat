# RCCN User Communication Application

This application handles bidirectional CCSDS frame communication with configurable input/output routing through virtual channels.
Packets within frames can be processed and routed between ROS2 topics and UDP sockets.

## Configuration

The application is configured via YAML file with two main sections:

### Frames Configuration
```yaml
frames:
  in:
    frame_kind: <type>     # Kind of incoming frames (e.g. TC)
    transport:
      kind: <protocol>     # Transport protocol (e.g. udp)
      bind: <address>      # Local binding address for receiving

  out:
    frame_kind: <type>     # Kind of outgoing frames (e.g. USLP)
    transport:
      kind: <protocol>     # Transport protocol (e.g. udp) 
      send: <address>      # Default send address
```

### Virtual Channels
```yaml
virtual_channels:
  - id: <number>           # Unique channel identifier
    name: <string>         # Channel name for logging
    
    in_transport:          # Input configuration
      kind: <type>         # Input protocol (ros2/udp)
      topic_pub: <topic>   # ROS2 publish topic (if ros2)
      send: <address>      # UDP send address (if udp)
    
    out_transport:         # Output configuration
      kind: <type>         # Output protocol (ros2/udp)
      topic_sub: <topic>   # ROS2 subscribe topic (if ros2)
      bind: <address>      # UDP bind address (if udp)
```

Each virtual channel is given an ID which is included in the frames, and a name for easier logging and debugging.

## Usage

1. Create a config file defining your desired:
   - CCSDS Frame types and transport for input/output
   - Virtual channels with their routing rules

2. Each virtual channel can:
   - Publish/Subscribe to ROS2 topics
   - Send/Receive on UDP ports

3. The application will:
   - Receive frames on the configured input transport
   - Route frame contents through appropriate virtual channels
   - Receive packets from the out side of virtual channels, pack them into frames and send them via the configured output transport

## Example Configuration

See `etc/config.yaml` for a working example that:
- Receives TC frames on UDP port 10018
- Sends USLP frames to UDP port 10015
- Routes messages through two virtual channels:
  1. A "bus_realtime" channel using ROS2 topics
  2. A "cfdp" channel using UDP ports 2000/3000
