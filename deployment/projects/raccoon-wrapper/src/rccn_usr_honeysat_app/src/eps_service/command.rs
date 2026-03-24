use binary_serde::{BinarySerde, Endianness};
use rccn_usr::service::{CommandParseError, CommandParseResult, ServiceCommand};
use satrs::spacepackets::ecss::{tc::PusTcReader, PusPacket};

pub mod eps_command {
    use binary_serde::{binary_serde_bitfield, BitfieldBitOrder};

    #[binary_serde_bitfield(order = BitfieldBitOrder::MsbFirst)]
    #[derive(Debug, PartialEq)]
    pub struct Args {
    }
}

pub enum Command {
    EPSCommand(eps_command::Args),
}

impl ServiceCommand for Command {
    fn from_pus_tc(tc: &PusTcReader) -> CommandParseResult<Self>
    where
        Self: Sized,
    {
        println!("Parsing EPS command with subservice: {}", tc.subservice());
        let args = eps_command::Args::binary_deserialize(
            &tc.app_data(),
            Endianness::Big,
        )
        .map_err(|_| CommandParseError::Other)?;
        Ok(Command::EPSCommand(args))
    }
}
