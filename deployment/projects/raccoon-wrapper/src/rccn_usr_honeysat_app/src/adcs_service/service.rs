use byteorder::{ByteOrder, LittleEndian};
use rccn_usr::{pus::parameter_management_service::ParameterError, service::{AcceptanceResult, AcceptedTc, PusService, SubserviceTmData}};
use xtce_rs::bitbuffer::BitWriter;
use hs_zmq_interface::{hs_commands, zmq_interface::{self}};

use super::command;

pub struct ADCSService {
}

impl ADCSService {
    pub fn new() -> Self {
        Self { }
    }

    /// Get ADCS mag data as a vector of length 3
    /// x,y,z
    fn get_adcs_addr_mag(&self) -> Result<Vec<f32>, ParameterError> {
        // Send and receive command
        let response = zmq_interface::send_command(hs_commands::ADCS_MAGNETIC);

        // Handle zmq fault
        if response.is_err(){
            // Well ... we have to use this weird ParameterError implementation
            return Err(ParameterError::UnknownParameter(0));
        }

        let data = response.unwrap();
        let x = LittleEndian::read_f32(data[0..4].as_ref());
        let y = LittleEndian::read_f32(data[4..8].as_ref());
        let z = LittleEndian::read_f32(data[8..12].as_ref());

        Ok(Vec::from([x, y, z]))
    }

    /// Get ADCS gyr data as a vector of length 3
    /// x,y,z
    fn get_adcs_addr_gyr(&self) -> Result<Vec<f32>, ParameterError> {
        // Send and receive command
        let response = zmq_interface::send_command(hs_commands::ADCS_GYRO);

        // Handle zmq fault
        if response.is_err(){
            // Well ... we have to use this weird ParameterError implementation
            return Err(ParameterError::UnknownParameter(0));
        }

        let data = response.unwrap();
        let x = LittleEndian::read_f32(data[0..4].as_ref());
        let y = LittleEndian::read_f32(data[4..8].as_ref());
        let z = LittleEndian::read_f32(data[8..12].as_ref());

        Ok(Vec::from([x, y, z]))
    }

    /// Get ADCS sun data as an i32
    fn get_adcs_addr_sun(&self) -> Result<i32, ParameterError> {
        // Send and receive command
        let response = zmq_interface::send_command(hs_commands::ADCS_SUN);

        // Handle zmq fault
        if response.is_err(){
            // Well ... we have to use this weird ParameterError implementation
            return Err(ParameterError::UnknownParameter(0));
        }

        let received_value = LittleEndian::read_i32(response.unwrap().as_ref());
        Ok(received_value)
    }
}

impl PusService for ADCSService {
    type CommandT = command::Command;

    fn handle_tc(&mut self, mut tc: AcceptedTc, cmd: Self::CommandT) -> AcceptanceResult {
        match cmd {
            Self::CommandT::MAGCommand(_) => {
                tc.handle_with_tm(||{
                    println!("Received ADCS MAG service request");

                    let mut data = [0u8; 3 * 4];
                    let mut writer = BitWriter::wrap(&mut data);
                    let mag_data = self.get_adcs_addr_mag()?;

                    for value in mag_data {
                        writer.write_bytes(value.to_le_bytes().as_ref())
                            .map_err(ParameterError::WriteError)?;
                    }

                    Ok::<SubserviceTmData, ParameterError>(SubserviceTmData{
                        subservice: 0,
                        data: Vec::from(&data),
                    })
                })
            },
            Self::CommandT::GYRCommand(_) => {
                tc.handle_with_tm(||{
                    println!("Received ADCS GYR service request");

                    let mut data = [0u8; 3 * 4];
                    let mut writer = BitWriter::wrap(&mut data);
                    let gyr_data = self.get_adcs_addr_gyr()?;

                    for value in gyr_data {
                        writer.write_bytes(value.to_le_bytes().as_ref())
                            .map_err(ParameterError::WriteError)?;
                    }

                    Ok::<SubserviceTmData, ParameterError>(SubserviceTmData{
                        subservice: 1,
                        data: Vec::from(&data),
                    })
                })
            },
            Self::CommandT::SUNCommand(_) => {
                tc.handle_with_tm(||{
                    println!("Received ADCS SUN service request");

                    let mut data = [0u8; 4];
                    let mut writer = BitWriter::wrap(&mut data);
                    let sun_data = self.get_adcs_addr_sun()?;

                    writer.write_bits(sun_data as u64, 32)
                        .map_err(ParameterError::WriteError)?;

                    Ok::<SubserviceTmData, ParameterError>(SubserviceTmData{
                        subservice: 2,
                        data: Vec::from(&data),
                    })
                })
            },
        }
    }

    fn service() -> u8 {
        133
    }
}

#[test]
fn test_get_mag() {
    let adcs = ADCSService::new();

    let magnetic = adcs.get_adcs_addr_mag().unwrap();
    println!("X:    {:6}mG", magnetic[0]);
    println!("Y:    {:6}mG", magnetic[1]);
    println!("Z:    {:6}mG", magnetic[2]);
}

#[test]
fn test_get_gyr() {
    let adcs = ADCSService::new();

    let gyro = adcs.get_adcs_addr_gyr().unwrap();
    println!("X:    {:6}mG", gyro[0]);
    println!("Y:    {:6}mG", gyro[1]);
    println!("Z:    {:6}mG", gyro[2]);
}

#[test]
fn test_get_sun() {
    let adcs = ADCSService::new();

    let sun = adcs.get_adcs_addr_sun();
    println!("Sun: {}", sun.unwrap())
}