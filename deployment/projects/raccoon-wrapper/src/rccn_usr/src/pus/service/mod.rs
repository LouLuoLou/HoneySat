mod macros;
pub mod util;

use crate::{
    impl_verification_sender,
    time::TimestampHelper,
    types::{RccnEcssTmSender, Sender},
};
use satrs::{
    pus::verification::{TcStateAccepted, TcStateStarted},
    spacepackets::{
        ecss::{tc::PusTcReader, PusError, PusPacket},
        CcsdsPacket,
    },
};
use satrs::{
    pus::{
        verification::{
            FailParams, TcStateNone, VerificationReporter, VerificationReporterCfg,
            VerificationReportingProvider, VerificationToken,
        },
        EcssTmSender, EcssTmtcError,
    },
    spacepackets::{
        ecss::{
            tm::{PusTmCreator, PusTmSecondaryHeader},
            EcssEnumU8, EcssEnumeration,
        },
        PacketId, PacketSequenceCtrl, PacketType, SequenceFlags, SpHeader,
    },
    ComponentId,
};
use hs_zmq_interface::zmq_interface::{self, is_satellite_reachable};
use std::sync::{Arc, Mutex};
use rand;

#[derive(Clone)]
pub struct PusAppBase {
    pub apid: u16,
    pub verification_reporter: VerificationReporter,
    pub timestamp_helper: TimestampHelper,
    pub component_id: ComponentId,
    pub msg_counter: Arc<Mutex<u16>>,
}

impl PusAppBase {
    pub fn new(
        apid: u16,
        component_id: ComponentId,
    ) -> Self {
        let verification_reporter_cfg =
            VerificationReporterCfg::new(apid, 1, 1, 100).expect("Invalid APID");

        Self {
            apid,
            timestamp_helper: TimestampHelper::new(),
            verification_reporter: VerificationReporter::new(
                component_id,
                &verification_reporter_cfg,
            ),
            component_id,
            msg_counter: Arc::new(Mutex::new(0u16)),
        }
    }

    pub fn new_reply(&self, service: u8, tx: Sender) -> CommandReplyBase {
        CommandReplyBase {
            app: self.clone(),
            service,
            tx
        }
    }
}

#[derive(Clone)]
pub struct CommandReplyBase {
    pub app: PusAppBase,
    pub service: u8,
    pub tx: Sender,
}

impl CommandReplyBase {
    pub fn get_tm_sender(&self) -> RccnEcssTmSender {
        RccnEcssTmSender {
            channel: self.tx.clone(),
            msg_counter: self.app.msg_counter.clone(),
        }
    }

    #[rustfmt::skip]
    impl_verification_sender!(acceptance, VerificationToken<TcStateNone>, VerificationToken<TcStateAccepted>);
    #[rustfmt::skip]
    impl_verification_sender!(start, VerificationToken<TcStateAccepted>, VerificationToken<TcStateStarted>);
    impl_verification_sender!(completion, VerificationToken<TcStateStarted>, ());

    pub fn create_tm<'ts, 'd>(
        &'ts self,
        subservice: u8,
        src_data: &'d [u8],
    ) -> PusTmCreator<'ts, 'd> {
        // TODO: destination ID not used
        PusTmCreator::new(
            SpHeader::new(
                PacketId::new(PacketType::Tm, true, self.app.apid),
                PacketSequenceCtrl::new(SequenceFlags::Unsegmented, 0),
                0,
            ),
            PusTmSecondaryHeader::new(
                self.service,
                subservice,
                0,
                0,
                self.app.timestamp_helper.stamp(),
            ),
            src_data,
            true,
        )
    }

    pub fn send_tm<'ts, 'd>(&'ts self, tm: PusTmCreator<'ts, 'd>) -> Result<(), EcssTmtcError> {
        self.get_tm_sender()
            .send_tm(0, satrs::pus::PusTmVariant::Direct(tm))
    }
}

#[derive(Debug, Clone)]
pub enum CommandParseError {
    UnknownSubservice(u8),
    Other,
}

pub type CommandParseResult<T> = Result<T, CommandParseError>;

#[derive(Debug, Clone)]
#[repr(u8)]
pub enum AcceptanceError {
    PusError(PusError) = 1,
    UnknownApid(u16),
    UnknownService(u8),
    UnknownSubservice(u8),
    CommandParseError(CommandParseError),
    ArgumentError,
    ServiceDisconnected,
    SendVerificationTmFailed,
}

impl Into<EcssEnumU8> for AcceptanceError {
    fn into(self) -> EcssEnumU8 {
        let tag = match self {
            AcceptanceError::PusError(_) => 1,
            AcceptanceError::UnknownApid(_) => 2,
            AcceptanceError::UnknownService(_) => 3,
            AcceptanceError::UnknownSubservice(_) => 4,
            AcceptanceError::CommandParseError(_) => 5,
            AcceptanceError::ArgumentError => 6,
            AcceptanceError::ServiceDisconnected => 7,
            AcceptanceError::SendVerificationTmFailed => 8,
        };

        EcssEnumU8::new(tag)
    }
}

/// Represents the possible outcomes of a successfully accepted command.
#[derive(Debug, PartialEq)]
pub enum CommandExecutionStatus {
    /// The task requested by the command has been started, but has not finished executing.
    Started,
    /// The task has been started and finished successfully.
    Completed,
    /// The task was started, but failed immediately.
    Failed,
}

pub type AcceptanceResult = Result<CommandExecutionStatus, AcceptanceError>;

pub trait ServiceCommand {
    fn from_pus_tc(tc: &PusTcReader) -> CommandParseResult<Self>
    where
        Self: Sized;
}

pub trait PusService {
    type CommandT: ServiceCommand;

    fn service() -> u8;

    fn handle_tc(&mut self, tc: AcceptedTc, cmd: Self::CommandT) -> AcceptanceResult;

    fn handle_tc_bytes(&mut self, bytes: &[u8], mut base: CommandReplyBase) -> AcceptanceResult {
        // ST[01] verification util
        let mut reporter = base.app.verification_reporter.clone();

        let pus_tc = match PusTcReader::new(&bytes) {
            Err(e) => {
                // Could not parse the incoming bytes as a PUS TC.
                // Since we don't know what we received, we also shouldn't send an error back.
                Err(AcceptanceError::PusError(e))
            }
            Ok((tc, _size)) => Ok(tc),
        }?;

        let token = reporter.add_tc(&pus_tc);
        base.app.timestamp_helper.update_from_now();

        // Check if the TC is destined for this APID
        if pus_tc.sp_header().apid() != base.app.apid {
            // It's not. Return early but don't send an acceptance failure.
            return Err(AcceptanceError::UnknownApid(pus_tc.sp_header().apid()));
        }

        // Check if the TC is destined for this service
        if pus_tc.service() != Self::service() {
            // It's not. Return early but don't send an acceptance failure
            // (there may be other services on this APID) that can respond to this.
            return Err(AcceptanceError::UnknownService(pus_tc.service()));
        }

        // Try to parse the TC using the service's CommandT
        // Send an acceptance failure TM frame if we couldn't parse the TC
        let svc_cmd = Self::CommandT::from_pus_tc(&pus_tc).map_err(|parse_error| {
            let err = AcceptanceError::CommandParseError(parse_error);

            // Send acceptance failure
            let err_code: EcssEnumU8 = err.clone().into();
            let send_result = base.send_acceptance_failure(token, &err_code, &[]);
            if let Err(e) = send_result {
                println!("Error sending acceptance failure TM: {e}");
            };

            err
        })?;

        std::thread::sleep(std::time::Duration::from_millis((500i128 + rand::Rng::gen_range(&mut rand::thread_rng(), -250i128..=250i128)).max(0) as u64));
        base.app.timestamp_helper.update_from_now();

        if ! is_satellite_reachable() {
            return Err(AcceptanceError::SendVerificationTmFailed)
        }



        // Send TC accepted telemetry, get TC accepted token
        let accepted_token = base.send_acceptance_success(token).map_err(|err| {
            println!("Error sending acceptance success telemetry: {err}");
            AcceptanceError::SendVerificationTmFailed
        })?;

        let tc = AcceptedTc::new(base, accepted_token);
        self.handle_tc(tc, svc_cmd)
    }
}

pub struct SubserviceTmData {
    pub subservice: u8,
    pub data: Vec<u8>,
}

pub struct AcceptedTc {
    pub base: CommandReplyBase,
    pub token: VerificationToken<TcStateAccepted>,
}

impl AcceptedTc {
    pub fn new(base: CommandReplyBase, token: VerificationToken<TcStateAccepted>) -> Self {
        Self { base, token }
    }

    pub fn handle<F>(&self, f: F) -> AcceptanceResult
    where
        F: FnOnce() -> bool,
    {
        let started_token = self.base.send_start_success(self.token).unwrap();

        let result = f();

        if result {
            self.base.send_completion_success(started_token).unwrap();
            Ok(CommandExecutionStatus::Completed)
        } else {
            self.base
                .send_completion_failure(started_token, &EcssEnumU8::new(1), &[])
                .unwrap();
            Ok(CommandExecutionStatus::Failed)
        }
    }

    pub fn handle_with_tm<E, F>(&mut self, f: F) -> AcceptanceResult
    where
        F: FnOnce() -> Result<SubserviceTmData, E>,
    {
        let started_token = self.base.send_start_success(self.token).unwrap();
        std::thread::sleep(std::time::Duration::from_millis((100i128 + rand::Rng::gen_range(&mut rand::thread_rng(), -50i128..=50i128)).max(0) as u64));
        match f() {
            Err(_) => {
                self.base
                    .send_completion_failure(started_token, &EcssEnumU8::new(1), &[])
                    .unwrap();
                Ok(CommandExecutionStatus::Failed)
            }
            Ok(tm_data) => {
                self.base.send_completion_success(started_token).unwrap();

                self.base.app.timestamp_helper.update_from_now();
                let tm = self.base.create_tm(tm_data.subservice, &tm_data.data);
                self.base.send_tm(tm).expect("could not send TM response");

                Ok(CommandExecutionStatus::Completed)
            }
        }
    }
}
