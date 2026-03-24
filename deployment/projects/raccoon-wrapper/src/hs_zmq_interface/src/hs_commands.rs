// SatellitePersonality Command Settings
pub const SIM_OBC_ID: u8 = 0x01;
pub const SIM_EPS_ID: u8 = 0x02;
pub const SIM_ADCS_ID: u8 = 0x03;
pub const SIM_CAMERA_ID: u8 = 0x04;
pub const SIM_COMM_ID: u8 = 0xFF;

// OBC Commands
pub const OBC_TMP: &[u8] = &[SIM_OBC_ID, 0x00];

// EPS Commands
pub const EPS_BATTERY: &[u8] = &[SIM_EPS_ID, 0x00];


// ACDS Commands
pub const ADCS_MAGNETIC: &[u8] = &[SIM_ADCS_ID, 0x00];
pub const ADCS_GYRO: &[u8] = &[SIM_ADCS_ID, 0x01];
pub const ADCS_SUN: &[u8] = &[SIM_ADCS_ID, 0x02, 0x01]; // For some reason this one needs another parameter for printing 'print(f"Sun[{message[2]}] = {sun}")'

// COMM Commands
pub const COMM_GET: &[u8] = &[SIM_COMM_ID, 0x00];