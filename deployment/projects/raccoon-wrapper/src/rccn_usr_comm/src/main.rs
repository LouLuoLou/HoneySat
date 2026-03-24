use anyhow::{Context, Result};
use config::Config;
use tokio::sync::mpsc::{channel, Receiver, Sender};
use frame_processor::FrameProcessor;
use std::{collections::HashMap, sync::Arc};
use transport::{setup_rx_transport, setup_tx_transport, AsyncTransport, UdpTransport, ZenohTransport};

mod config;
mod frame_processor;
mod transport;

type VcId = u8;
type VcTxMap = HashMap<VcId, Sender<Vec<u8>>>;
type VcRxMap = HashMap<VcId, Receiver<Vec<u8>>>;

const CHANNEL_SIZE: usize = 32;

async fn setup_virtual_channels(
    config: Arc<Config>,
    processor: FrameProcessor,
    bytes_out_tx: Sender<Vec<u8>>,
    zenoh_transport: &ZenohTransport,
) -> Result<VcTxMap> {
    let mut vc_tx_map = VcTxMap::new();

    for vc in &config.virtual_channels {
        // Setup TX direction.
        // The TX direction means FRAMES IN -> VC DATA TX
        if let Some(tx) = &vc.tx_transport {
            let (tx_in, tx_out) = channel(CHANNEL_SIZE);
            setup_tx_transport(tx, tx_out, zenoh_transport).await?;
            vc_tx_map.insert(vc.id, tx_in);
        }

        // Setup RX direction.
        // Here we receive messages from the virtual channel that should be
        // converted into frames. 
        // We call it the RX direction because the `rccn_usr_comm` listens on
        // a given transport for messages from other applications.
        if let Some(rx) = &vc.rx_transport {
            let (rx_in, rx_out) = channel(CHANNEL_SIZE);
            setup_rx_transport(rx, rx_in, zenoh_transport).await?;

            // Clone relevant variables for the task we're about to spawn.
            let tx = bytes_out_tx.clone();
            let processor = processor.clone();
            let vc_id = vc.id;
            tokio::spawn(async move {
                processor.virtual_channel_rx_handler(rx_out, tx, vc_id).await
            });
        }
    }

    Ok(vc_tx_map)
}

#[tokio::main]
async fn main() -> Result<()> {
    let config_path = Config::find_config_file()?;
    println!("Using config file: {}", config_path.display());
    let config = Arc::new(Config::from_file(config_path)?);
    println!("Loaded configuration: {:#?}", config);

    // Set up Zenoh
    let session = zenoh::open(zenoh::Config::default()).await.unwrap();
    let zenoh_transport = ZenohTransport::new(session);

    // Create channels for frame I/O
    let (bytes_in_tx, bytes_in_rx) = channel(CHANNEL_SIZE);
    let (bytes_out_tx, bytes_out_rx) = channel(CHANNEL_SIZE);

    // Setup frame I/O transport
    setup_rx_transport(&config.frames.r#in.transport, bytes_in_tx, &zenoh_transport).await?;
    setup_tx_transport(&config.frames.out.transport, bytes_out_rx, &zenoh_transport).await?;

    // Setup frame processor
    let processor = FrameProcessor::new(config.clone());

    // Setup virtual channels.
    // We get a Virtual Channel TX map, which is used by the frame processor
    // to determine which Sender to send VC data to.
    let vc_tx_map = setup_virtual_channels(
        config.clone(),
        processor.clone(),
        bytes_out_tx.clone(),
        &zenoh_transport,
    )
    .await?;

    processor.process_incoming_frames(bytes_in_rx, &vc_tx_map).await?;

    // Keep main thread running
    std::thread::park();
    println!("Shutting down...");

    Ok(())
}
