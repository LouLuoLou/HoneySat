use rccn_usr::types::VcId;

use serde::{Deserialize, Serialize};
use std::{io, path::{Path, PathBuf}};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ConfigError {
    #[error("IO error: {0}")]
    Io(#[from] io::Error),
    #[error("YAML parsing error: {0}")]
    Yaml(#[from] serde_yaml::Error),
    #[error("Config validation error: {0}")]
    Validation(String),
    #[error("Configuration file not found")]
    ConfigNotFound
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Copy)]
#[serde(rename_all = "lowercase")]
pub enum FrameKind {
    Tc,
    Uslp,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct FrameConfig {
    pub frame_kind: FrameKind,
    pub transport: RxTransport,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct FrameOutConfig {
    pub frame_kind: FrameKind,
    pub transport: TxTransport,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct Frames {
    pub spacecraft_id: u16,
    pub r#in: FrameConfig,
    pub out: FrameOutConfig,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct UdpTxTransport {
    pub send: String
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct UdpRxTransport {
    pub listen: String
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct ZenohTxTransport {
    pub key_pub: String, 
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct ZenohRxTransport {
    pub key_sub: String, 
}


#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum TxTransport {
    Udp(UdpTxTransport),
    Zenoh(ZenohTxTransport)
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum RxTransport {
    Udp(UdpRxTransport),
    Zenoh(ZenohRxTransport)
}



#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct VirtualChannel {
    pub id: VcId,
    pub name: String,
    pub tx_transport: Option<TxTransport>,
    pub rx_transport: Option<RxTransport>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Config {
    pub frames: Frames,
    pub virtual_channels: Vec<VirtualChannel>,
}

impl Config {
    pub fn find_config_file() -> Result<PathBuf, ConfigError> {
        let paths = [
            "etc/config.yaml",
            "install/rccn_usr_comm/share/rccn_usr_comm/etc/config.yaml",
            "src/rccn_usr_comm/etc/config.yaml"
        ];

        for path in paths {
            let p = PathBuf::from(path);
            if p.exists() {
                return Ok(p)
            }
        }

        return Err(ConfigError::ConfigNotFound)
    }

    pub fn from_file<P: AsRef<Path>>(path: P) -> Result<Self, ConfigError> {
        let contents = std::fs::read_to_string(path)?;
        let config: Self = serde_yaml::from_str(&contents)?;
        config.validate()?;
        Ok(config)
    }

    fn validate(&self) -> Result<(), ConfigError> {
        // Validate frame types
        if self.frames.r#in.frame_kind != FrameKind::Tc {
            return Err(ConfigError::Validation(
                "Input frame kind must be TC".into(),
            ));
        }
        if self.frames.out.frame_kind != FrameKind::Uslp {
            return Err(ConfigError::Validation(
                "Output frame kind must be USLP".into(),
            ));
        }

        // Validate virtual channels: check IDs are unique and ROS2 output transports
        let mut seen_ids = std::collections::HashSet::new();
        for vc in &self.virtual_channels {
            if !seen_ids.insert(vc.id) {
                return Err(ConfigError::Validation(format!(
                    "Duplicate virtual channel ID: {}",
                    vc.id
                )));
            }
        }

        Ok(())
    }
}
