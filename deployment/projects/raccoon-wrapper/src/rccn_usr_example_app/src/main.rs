use anyhow::Result;
use example_service::service::ExampleService;
use rccn_usr::pus::app::PusApp;
use rccn_usr::zenoh::key_expr::OwnedKeyExpr;

mod example_service;

const APID: u16 = 42;

fn main() -> Result<()> {
    let mut app = PusApp::new(APID);

    app
        .add_tc_tm_channel(
            OwnedKeyExpr::new("vc/bus_realtime/rx").unwrap(),
            OwnedKeyExpr::new("vc/bus_realtime/tx").unwrap(),
        )
        .unwrap();

    let service = ExampleService::new();
    app.register_service(service);

    app.run();
    Ok(())
}
