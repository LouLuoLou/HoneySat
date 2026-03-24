use crate::stress_service::command::StressServiceCommand;
use futures::{executor::ThreadPool, task::SpawnExt};
use rccn_usr::{
    r2r::{self, thermal_test_msgs::action::StressTest},
    service::{AcceptanceResult, AcceptedTc, CommandExecutionStatus, PusService},
    transport::ros2::SharedNode,
};
use satrs::spacepackets::ecss::EcssEnumU8;

pub struct StressTestService {
    pool: ThreadPool,
    node: SharedNode,
}

impl StressTestService {
    pub fn new(node: SharedNode) -> Self {
        Self {
            pool: ThreadPool::new().unwrap(),
            node,
        }
    }
}

async fn send_stress_test_goal(
    node: SharedNode,
    tc: AcceptedTc,
    cmd: StressServiceCommand,
) -> Result<(), r2r::Error> {
    let client = node
        .lock()
        .expect("could not lock node to create client")
        .create_action_client::<StressTest::Action>("/stress_test")?;

    /*
    println!("Waiting for action service...");
    r2r::Node::is_available(&client)?.await.unwrap();
    println!("ACtion service available.");
    */

    let (test_type, duration) = match cmd {
        StressServiceCommand::Cpu(d) => ("CPU", d.seconds),
        StressServiceCommand::Ram(d) => ("RAM", d.seconds),
        StressServiceCommand::Io(d) => ("IO", d.seconds),
        StressServiceCommand::SdrRx(d) => ("SDR_RX", d.seconds),
        StressServiceCommand::SdrTx(d) => ("SDR_TX", d.seconds),
        StressServiceCommand::TcTest(d) => ("TC_TEST", d.seconds),
    };

    let (_goal, done, _feedback) = client
        .send_goal_request(StressTest::Goal {
            test_type: test_type.to_string(),
            duration: duration as i32,
            args: [].to_vec(),
        })?
        .await?;

    // Goal has started successfully
    let token = tc.base.send_start_success(tc.token).unwrap();

    let (_status, result) = done.await?;
    if result.success {
        println!("Goal succeded: {}", result.message);
        tc.base.send_completion_success(token).unwrap();
    } else {
        println!("Goal failed: {}", result.message);
        tc.base
            .send_completion_failure(token, &EcssEnumU8::new(1), &[])
            .unwrap();
    }

    Ok(())
}

impl PusService for StressTestService {
    type CommandT = StressServiceCommand;

    fn service() -> u8 {
        142
    }

    fn handle_tc(&mut self, tc: AcceptedTc, cmd: Self::CommandT) -> AcceptanceResult {
        println!("Stress service command {:?}", cmd);

        let node = self.node.clone();
        self.pool
            .spawn(async move {
                let _ = send_stress_test_goal(node, tc, cmd).await;
            })
            .unwrap();

        Ok(CommandExecutionStatus::Started)
    }
}
