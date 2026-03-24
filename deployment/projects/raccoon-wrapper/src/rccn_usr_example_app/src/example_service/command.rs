use binary_serde::{BinarySerde, Endianness};
use rccn_usr::service::{CommandParseError, CommandParseResult, ServiceCommand};
use satrs::spacepackets::ecss::{tc::PusTcReader, PusPacket};

pub mod generated_command_test {
    use binary_serde::{binary_serde_bitfield, BinarySerde, BitfieldBitOrder};

    #[binary_serde_bitfield(order = BitfieldBitOrder::MsbFirst)]
    #[derive(Debug, PartialEq)]
    pub struct Args {
        #[bits(8)]
        pub battery_num: u32,
        #[bits(5)]
        pub custom_length: u32,
        #[bits(8)]
        pub enum_arg: EnumArg,
        #[bits(4)]
        pub enumerated_arg_custom_type: EnumeratedArgCustomType,

        #[bits(7)]
        pub padding: u8,
    }

    #[derive(Debug, BinarySerde, PartialEq)]
    #[repr(u8)]
    pub enum EnumArg {
        OFF = 0,
        ON = 1,
        EXPLODE = 2,
    }

    #[derive(Debug, BinarySerde, PartialEq)]
    #[repr(u8)]
    pub enum EnumeratedArgCustomType {
        AUS = 0,
        EIN = 1,
        JA = 2,
    }
}

pub enum Command {
    GeneratedCommandTest(generated_command_test::Args),
}

impl ServiceCommand for Command {
    fn from_pus_tc(tc: &PusTcReader) -> CommandParseResult<Self>
    where
        Self: Sized,
    {
        match tc.subservice() {
            1 => {
                let args = generated_command_test::Args::binary_deserialize(
                    &tc.app_data(),
                    Endianness::Big,
                )
                .map_err(|_| CommandParseError::Other)?;
                Ok(Command::GeneratedCommandTest(args))
            }
            _ => Err(rccn_usr::service::CommandParseError::UnknownSubservice(
                tc.subservice(),
            )),
        }
    }
}

#[cfg(test)]
pub mod tests {
    use binary_serde::{recursive_array::RecursiveArray, BinarySerde, Endianness};

    use super::generated_command_test::{self, EnumArg, EnumeratedArgCustomType};

    #[test]
    fn test_generated_cmd_args() {
        let a = generated_command_test::Args {
            battery_num: 3,
            custom_length: 7,
            enum_arg: EnumArg::EXPLODE,
            enumerated_arg_custom_type: EnumeratedArgCustomType::EIN,
            padding: 0,
        };
        let a_bytes = a.binary_serialize_to_array(Endianness::Big);

        assert_eq!(a_bytes.as_slice(), [3, 56, 16, 128]);

        let b =
            generated_command_test::Args::binary_deserialize(a_bytes.as_slice(), Endianness::Big)
                .expect("deserialization failed");

        assert_eq!(a, b);
    }
}
