pub mod command;
pub mod service;

use std::sync::{Arc, Mutex};

use xtce_rs::bitbuffer::{BitBuffer, BitWriter, WriteError};

// TODO we cannot use thiserror:Error because xtce_rs::bitbuffer::WriteError does not implement Error
#[derive(Debug, PartialEq)]
pub enum ParameterError {
    UnknownParameter(u32),
    WriteError(WriteError),
}

pub trait PusParameters {
    fn get_parameter_as_be_bytes(
        &self,
        hash: u32,
        writer: &mut BitWriter,
    ) -> Result<usize, ParameterError>;
    fn set_parameter_from_be_bytes(&mut self, hash: u32, buffer: &mut BitBuffer) -> bool;
    fn get_parameter_size(&self, hash: u32) -> Option<usize>;
}

pub type SharedPusParameters = Arc<Mutex<dyn PusParameters + Send>>;

pub fn src_buffer_to_u64(src: &[u8], bits: usize) -> u64 {
    assert!(bits <= 64);
    assert!(src.len() <= 8);

    let mut dst = [0u8; 8];

    // Copy all src bytes into dst (assumed to be big endian)
    let start = dst.len() - src.len();
    let end = dst.len();
    dst[start..end].copy_from_slice(&src);

    // Convert to u64 and mask to only keep the bits we want
    let mut val = u64::from_be_bytes(dst);
    val &= (1 << bits) - 1;

    val
}
