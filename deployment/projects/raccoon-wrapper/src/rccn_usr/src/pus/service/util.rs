use satrs::spacepackets::{ecss::tc::{PusTcCreator, PusTcSecondaryHeader}, PacketId, PacketSequenceCtrl, PacketType, SequenceFlags, SpHeader};

pub fn create_pus_tc<'a>(apid: u16, service: u8, subservice: u8, data: &'a [u8]) -> PusTcCreator<'a> {
    PusTcCreator::new(
        SpHeader::new(
            PacketId::new(PacketType::Tc, true, apid),
            PacketSequenceCtrl::new(SequenceFlags::Unsegmented, 0),
            0,
        ),
        PusTcSecondaryHeader::new(service, subservice, 0xff, 0),
        &data, 
        true,
    )
}