use std::{thread::sleep, time::Duration};

use rccn_usr::service::{AcceptanceResult, AcceptedTc, PusService};

use super::command;

pub struct ExampleService {
}

impl ExampleService {
    pub fn new() -> Self {
        Self { }
    }
}

impl PusService for ExampleService {
    type CommandT = command::Command;

    fn handle_tc(&mut self, tc: AcceptedTc, cmd: Self::CommandT) -> AcceptanceResult {
        match cmd {
            command::Command::GeneratedCommandTest(args) => tc.handle(||{
                sleep(Duration::from_millis(2000));
                println!("Generated command test args: {args:?}");
                true
            })
        }
    }
    
    fn service() -> u8 {
        130
    }
}