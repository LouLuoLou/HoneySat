use std::env;
use zmq::Message;

use super::hs_commands::COMM_GET;

pub fn send_command(command: &[u8]) -> Result<Message, zmq::Error> {
    // Get HoneySat ip and port from ENV variable
    let hs_ip = env::var("HS_IP").unwrap_or("127.0.0.1".parse().unwrap());
    let hs_port = env::var("HS_PORT").unwrap_or("5555".parse().unwrap());
    let endpoint = format!("tcp://{hs_ip}:{hs_port}");

    // Create socket
    let ctx = zmq::Context::new();
    let socket = ctx.socket(zmq::REQ)?;

    // Set timeouts for connect, send and receive (1000 milliseconds = 1 seconds)
    socket.set_connect_timeout(1000)?;
    socket.set_sndtimeo(1000)?;
    socket.set_rcvtimeo(1000)?;

    // Connect to socket
    socket.connect(&*endpoint)?;

    // Send command
    socket.send(command, 0)?;

    // Get response
    let response = socket.recv_msg(0)?;
    return Ok(response);
}

pub fn is_satellite_reachable() -> bool {
    if env::var("ALWAYS_REACHABLE").is_ok() {
        return true;
    }
    // Send and receive command
    let response = send_command(COMM_GET);

    // Handle zmq fault
    if response.is_err() {
        return false;
    }

    let response = response.unwrap();
    if response.len() != 1 {
        return false;
    }
    // Check if response is 0
    return response[0] != 0;
}