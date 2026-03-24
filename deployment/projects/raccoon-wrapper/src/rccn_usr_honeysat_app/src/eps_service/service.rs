// use std::{thread::sleep, time::Duration};

use byteorder::{ByteOrder, LittleEndian};
use rccn_usr::{pus::parameter_management_service::ParameterError, service::{AcceptanceResult, AcceptedTc, PusService, SubserviceTmData}};
use xtce_rs::bitbuffer::BitWriter;
use hs_zmq_interface::{hs_commands, zmq_interface::{self}};

use super::command;

pub struct EPSService {
}

impl EPSService {
    pub fn new() -> Self {
        Self { }
    }

    /// Get EPS data as a vector of length 4
    /// voltage, current_in, current_out, temperature
    fn get_data(&self) -> Result<Vec<i32>, ParameterError> {
        // Send and receive command
        let response = zmq_interface::send_command(hs_commands::EPS_BATTERY);

        // Handle zmq fault
        if response.is_err(){
            // Well ... we have to use this weird ParameterError implementation
            return Err(ParameterError::UnknownParameter(0));
        }

        let data = response.unwrap();
        let voltage = LittleEndian::read_i32(data[0..4].as_ref());
        let current_in = LittleEndian::read_i32(data[4..8].as_ref());
        let current_out = LittleEndian::read_i32(data[8..12].as_ref());
        let temperature = LittleEndian::read_i32(data[12..16].as_ref());

        Ok(vec![voltage, current_in, current_out, temperature])
    }
}

impl PusService for EPSService {
    type CommandT = command::Command;

    fn handle_tc(&mut self, mut tc: AcceptedTc, _cmd: Self::CommandT) -> AcceptanceResult {
        // There's only one tc in this service. No need to match on subservice.
        tc.handle_with_tm(||{
            println!("Received EPS service request");

            let mut data = [0u8; 4 * 4];
            let mut writer = BitWriter::wrap(&mut data);
            let eps_data = self.get_data()?;

            for value in eps_data {
                writer.write_bits(value as u64, 32)
                    .map_err(ParameterError::WriteError)?;
            }

            Ok::<SubserviceTmData, ParameterError>(SubserviceTmData{
                subservice: 0,
                data: Vec::from(&data),
            })
        })
    }

    fn service() -> u8 {
        132
    }
}

#[test]
fn test_get_battery() {
    let eps = EPSService::new();

    let battery = eps.get_data().unwrap();
    println!("Voltage:      {:6}V", battery[0]);
    println!("Current In:   {:6}A", battery[1]);
    println!("Current Out:  {:6}A", battery[2]);
    println!("Temperature:  {:6}°", battery[3]);
}