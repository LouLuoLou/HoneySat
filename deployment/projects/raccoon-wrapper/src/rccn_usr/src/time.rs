// Taken from https://github.com/us-irs/sat-rs/blob/main/satrs-example/src/lib.rs

//use satrs::spacepackets::time::{cds::CdsTime, TimeWriter};

use satrs::spacepackets::time::{cuc::{CucTime, FractionalResolution}, TimeWriter};

#[derive(Clone)]
pub struct TimestampHelper {
    timestamp: [u8; 8], // 1 byte pfield, 4 bytes coarse, 3 bytes fine time
}

impl TimestampHelper {
    pub fn new() -> Self {
        Self {
            timestamp: [0u8; 8]
        }
    }

    pub fn stamp(&self) -> &[u8] {
        &self.timestamp
    }

    pub fn update_from_now(&mut self) {
        // TODO: Get leap second information from somewhere
        let leap_seconds = 0;
        match CucTime::now(FractionalResolution::SixtyNs, leap_seconds) {
            Ok(cuc) => {
                cuc.write_to_bytes(&mut self.timestamp)
                .expect("Writing timestamp failed");

            }
            Err(_) => {
                // TODO propagate error
            }
        }
    }
}