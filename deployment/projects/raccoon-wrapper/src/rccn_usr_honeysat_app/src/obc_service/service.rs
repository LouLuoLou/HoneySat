// use std::{thread::sleep, time::Duration};
use hs_zmq_interface::{hs_commands, zmq_interface};

use rccn_usr::{pus::parameter_management_service::ParameterError, service::{AcceptanceResult, AcceptedTc, PusService, SubserviceTmData}};
use xtce_rs::bitbuffer::BitWriter;
use byteorder::{ByteOrder, LittleEndian};
use hs_zmq_interface::{self};

use super::command;

pub struct OBCService {
}

impl OBCService {
    pub fn new() -> Self {
        Self { }
    }

    fn get_temperature(&self) -> Result<i32, ParameterError> {
        // Send and receive command
        let response = zmq_interface::send_command(hs_commands::OBC_TMP);

        // Handle zmq fault
        if response.is_err(){
            // Well ... we have to use this weird ParameterError implementation
            return Err(ParameterError::UnknownParameter(0));
        }

        let received_value = LittleEndian::read_i32(response.unwrap().as_ref());
        Ok(received_value)
    }
}

impl PusService for OBCService {
    type CommandT = command::Command;

    fn handle_tc(&mut self, mut tc: AcceptedTc, _cmd: Self::CommandT) -> AcceptanceResult {
        // There's only one tc in this service. No need to match on subservice.
        tc.handle_with_tm(||{
            println!("Received OBC service request");

            let mut data = [0u8; 4];
            let mut writer = BitWriter::wrap(&mut data);
            let temp = self.get_temperature()?;
            let mut x = 0;

            writer.write_bits(temp as u64, 32)
                .map_err(ParameterError::WriteError)
                .map(|_| x += 32)?;

            Ok::<SubserviceTmData, ParameterError>(SubserviceTmData{
                subservice: 0,
                data: Vec::from(&data),
            })
        })
    }

    fn service() -> u8 {
        131
    }
}

#[test]
fn test_get_temperature() {
    let obcs = OBCService::new();

    let temp = obcs.get_temperature();
    println!("Temp: {}", temp.unwrap())
}