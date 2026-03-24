use rccn_usr::service::{CommandParseError, CommandParseResult, ServiceCommand};
use satrs::spacepackets::ecss::{tc::PusTcReader, PusPacket};

pub mod adcs_command {
    use binary_serde::{binary_serde_bitfield, BitfieldBitOrder};

    #[binary_serde_bitfield(order = BitfieldBitOrder::MsbFirst)]
    #[derive(Debug, PartialEq)]
    pub struct Args {
    }
}

pub enum Command {
    MAGCommand(adcs_command::Args),
    GYRCommand(adcs_command::Args),
    SUNCommand(adcs_command::Args),
}

impl ServiceCommand for Command {
    fn from_pus_tc(tc: &PusTcReader) -> CommandParseResult<Self>
    where
        Self: Sized,
    {
        println!("Parsing ADCS command with subservice: {}", tc.subservice());
        match tc.subservice() {
            0 => Ok(Command::MAGCommand(adcs_command::Args{})),
            1 => Ok(Command::GYRCommand(adcs_command::Args{})),
            2 => Ok(Command::SUNCommand(adcs_command::Args{})),
            _ => Err(CommandParseError::UnknownSubservice(tc.subservice())),
        }
    }
}
