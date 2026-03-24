use adcs_service::service::ADCSService;
use anyhow::Result;
use eps_service::service::EPSService;
use obc_service::service::OBCService;
use rccn_usr::pus::app::PusApp;
use rccn_usr::zenoh::key_expr::OwnedKeyExpr;

mod obc_service;
mod eps_service;
mod adcs_service;

const APID: u16 = 42;

fn main() -> Result<()> {
    let mut app = PusApp::new(APID);

    app
        .add_tc_tm_channel(
            OwnedKeyExpr::new("vc/bus_realtime/rx").unwrap(),
            OwnedKeyExpr::new("vc/bus_realtime/tx").unwrap(),
        )
        .unwrap();

    let obc_service = OBCService::new();
    app.register_service(obc_service);

    let eps_service = EPSService::new();
    app.register_service(eps_service);

    let adcs_service = ADCSService::new();
    app.register_service(adcs_service);

    app.run();
    Ok(())
}
