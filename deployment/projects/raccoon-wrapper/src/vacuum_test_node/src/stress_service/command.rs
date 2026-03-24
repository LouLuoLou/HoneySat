use binary_serde::BinarySerde;
use rccn_usr::service::{CommandParseError, CommandParseResult, ServiceCommand};
use satrs::spacepackets::ecss::{tc::PusTcReader, PusPacket};

pub mod stress_command {
    use binary_serde::BinarySerde;

    #[derive(Debug, BinarySerde)]
    pub struct DurationArgs {
        pub seconds: u16,
    }
}

#[allow(dead_code)]
#[derive(Debug)]
pub enum StressServiceCommand {
    Cpu(stress_command::DurationArgs),
    Ram(stress_command::DurationArgs),
    Io(stress_command::DurationArgs),
    SdrRx(stress_command::DurationArgs),
    SdrTx(stress_command::DurationArgs),
    TcTest(stress_command::DurationArgs),
}

impl ServiceCommand for StressServiceCommand {
    fn from_pus_tc(tc: &PusTcReader) -> CommandParseResult<Self> {
        let duration = stress_command::DurationArgs::binary_deserialize(
            tc.app_data(),
            binary_serde::Endianness::Big,
        )
        .map_err(|_| CommandParseError::Other)?;

        match tc.subservice() {
            1 => Ok(Self::Cpu(duration)),
            2 => Ok(Self::Ram(duration)),
            3 => Ok(Self::Io(duration)),
            4 => Ok(Self::SdrRx(duration)),
            5 => Ok(Self::SdrTx(duration)),
            6 => Ok(Self::TcTest(duration)),
            _ => Err(CommandParseError::UnknownSubservice(tc.subservice())),
        }
    }
}
