use anyhow::Result;
use rccn_usr::{config::VirtualChannel, transport::ros2::new_shared_ros2_node};
use rccn_usr_pus::app::PusApp;
use stress_service::service::StressTestService;

mod stress_service;

fn main() -> Result<()> {
    let node = new_shared_ros2_node("vacuum_test_node", &"/")?;
    let mut app = PusApp::new_with_ros2_node(42, node.clone());

    app.add_virtual_channel(&VirtualChannel::on_ros2_topic(0, "bus_realtime"))?;

    let stress_service = StressTestService::new(node.clone());
    app.register_service(stress_service);

    app.run();
    Ok(())
}
