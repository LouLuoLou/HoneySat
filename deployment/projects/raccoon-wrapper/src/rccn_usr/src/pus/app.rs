use std::{
    sync::{Arc, Mutex},
    thread::{self, JoinHandle},
};

use tokio::sync::mpsc::channel;
use zenoh::{key_expr::OwnedKeyExpr, Session, Wait};

use crate::{
    pus::service::{AcceptanceResult, CommandReplyBase, PusAppBase, PusService},
    types::Sender,
};

type ServiceHandler = Box<dyn FnMut(&[u8], CommandReplyBase) -> AcceptanceResult + Send>;

#[derive(Debug)]
pub enum TaskError {
    ChannelDisconnected,
}

pub struct PusApp {
    session: Session,
    handlers: Arc<Mutex<Vec<(u8, ServiceHandler)>>>,
    base: PusAppBase,
    task_handles: Vec<JoinHandle<Result<(), TaskError>>>,
}

impl PusApp {
    pub fn new_with_session(apid: u16, session: Session) -> Self {
        Self {
            handlers: Arc::new(Mutex::new(Vec::new())),
            base: PusAppBase::new(apid, 0),
            session,
            task_handles: Vec::new(),
        }
    }

    pub fn new(apid: u16) -> Self {
        let session = zenoh::open(zenoh::Config::default()).wait().unwrap();
        Self::new_with_session(apid, session)
    }

    pub fn register_service<S: PusService + 'static + Send>(&mut self, mut service: S) {
        let handler: ServiceHandler =
            Box::new(move |bytes, base| service.handle_tc_bytes(bytes, base));

        self.handlers.lock().unwrap().push((S::service(), handler));
    }

    fn handle_tc_internal(
        app_base: &PusAppBase,
        handlers: &mut Vec<(u8, ServiceHandler)>,
        data: &[u8],
        tx: Sender,
    ) -> Vec<AcceptanceResult> {
        handlers
            .iter_mut()
            // Call each service handler
            .map(|(service_id, handler)| {
                let reply_base = app_base.new_reply(*service_id, tx.clone());
                handler(data, reply_base)
            })
            // Gather all the AcceptanceResults
            .collect()
    }

    pub fn add_tc_tm_channel(
        &mut self,
        tc_subscribe_key: OwnedKeyExpr,
        tm_publish_key: OwnedKeyExpr,
    ) -> Result<(), zenoh::Error> {
        let subscriber = self.session.declare_subscriber(tc_subscribe_key).wait()?;
        let publisher = self.session.declare_publisher(tm_publish_key).wait()?;

        let (tm_tx, mut tm_rx) = channel(1);
        let app_base = self.base.clone();
        let handlers = self.handlers.clone();

        // Spawn a thread that will subscribe to a key on Zenoh
        // where TCs are published.
        // When a TC is received, call `Self::handle_tc_internal`.

        self.task_handles.push(thread::spawn(move || {
            loop {
                // Block until we receive a TC on the Zenoh subscriber
                let tc = subscriber.recv();

                // Check if we have received a channel error
                if tc.is_err() {
                    println!("Error, exiting");
                    return Err(TaskError::ChannelDisconnected);
                }

                // We have received a TC, get the bytes payload.
                let tc = tc.unwrap();
                let tc_bytes = tc.payload().to_bytes();

                // Call the handlers.
                let mut handlers = handlers.lock().unwrap();
                Self::handle_tc_internal(&app_base, &mut handlers, &tc_bytes, tm_tx.clone());

                // TODO check if we get at least one Completed status
            }
        }));

        // Spawn a thread that waits for the service to publish TM
        // packets and forwards them to Zenoh.

        self.task_handles.push(thread::spawn(move || {
            loop {
                let tm = tm_rx.blocking_recv();
                if tm.is_none() {
                    println!("Got None, exiting");
                    return Err(TaskError::ChannelDisconnected);
                }

                // We have received TM packet that the service wants to send.
                // Publish it on Zenoh.
                let tm = tm.unwrap();
                publisher.put(tm).wait().unwrap();
            }
        }));

        Ok(())
    }

    // Mainly for testing purposes
    pub fn handle_tc(&mut self, data: &[u8], tx: Sender) -> Vec<AcceptanceResult> {
        Self::handle_tc_internal(&self.base, &mut self.handlers.lock().unwrap(), data, tx)
    }

    pub fn run(self) {
        for jh in self.task_handles.into_iter() {
            let _r = jh.join().unwrap().unwrap();
        }
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use super::*;
    use crate::pus::parameter_management_service::{
        service::ParameterManagementService, ParameterError, PusParameters,
    };
    use crate::service::{util::create_pus_tc, CommandExecutionStatus};
    use rccn_usr_pus_macros::PusParameters;
    use satrs::spacepackets::ecss::WritablePusPacket;
    use tokio::sync::mpsc::channel;
    use xtce_rs::bitbuffer::{BitBuffer, BitWriter};

    #[derive(PusParameters)]
    struct TestParameters {
        #[hash(0x1234)]
        value: u32,
    }

    #[test]
    fn test_register_and_handle_service() {
        let (tm_tx, tm_rx) = channel(4);

        // Create PusApp and register ParameterManagementService
        let mut app = PusApp::new(1);
        let parameters = Arc::new(Mutex::new(TestParameters { value: 42 }));
        let service = ParameterManagementService::new(parameters);
        app.register_service(service);

        // Create a test TC for parameter reporting
        let mut tc_data = [0u8; 128];
        tc_data[0] = 0; // Number of parameters MSB
        tc_data[1] = 1; // Number of parameters LSB
        tc_data[2] = 0; // Parameter hash
        tc_data[3] = 0;
        tc_data[4] = 0x12;
        tc_data[5] = 0x34;

        let tc = create_pus_tc(1, 20, 1, &tc_data);
        let tc_bytes = tc.to_vec().unwrap();

        // Handle TC
        let results = app.handle_tc(&tc_bytes, tm_tx);

        // Check that a service returned Completed
        assert!(results
            .iter()
            .any(|r| matches!(r, Ok(CommandExecutionStatus::Completed))));

        // Check that 4 messages were sent to TM rx (accepted, started, completed, parameter TM)
        assert_eq!(tm_rx.len(), 4);
    }
}
