use async_trait::async_trait;
use std::io;
use std::net::{AddrParseError, SocketAddr};
use std::str::FromStr;
use thiserror::Error;
use tokio::net::UdpSocket;
use tokio::sync::mpsc::{Receiver, Sender};
use zenoh::{key_expr::OwnedKeyExpr, Session, Wait};
use anyhow::{Context, Error, Result};

use crate::config;

#[derive(Error, Debug)]
pub enum TransportError {
    #[error("Invalid UDP address: {0}")]
    UdpAddrParse(#[from] std::net::AddrParseError),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Zenoh error: {0}")]
    Zenoh(#[from] zenoh::Error),
}

pub const TRANSPORT_BUFFER_SIZE: usize = 8096;

pub async fn setup_rx_transport(
    transport: &config::RxTransport,
    tx: Sender<Vec<u8>>,
    zenoh_transport: &ZenohTransport,
) -> Result<()> {
    match transport {
        config::RxTransport::Udp(udp) => {
            UdpTransport
                .start_reader(tx, udp.listen.clone())
                .await
                .context(format!("Failed to bind to {0}", udp.listen))?;
        }
        config::RxTransport::Zenoh(zenoh) => {
            zenoh_transport
                .start_reader(tx, zenoh.key_sub.clone())
                .await
                .unwrap()
        }
    }
    Ok(())
}

pub async fn setup_tx_transport(
    transport: &config::TxTransport,
    rx: Receiver<Vec<u8>>,
    zenoh_transport: &ZenohTransport,
) -> Result<()> {
    match transport {
        config::TxTransport::Udp(udp) => {
            UdpTransport
                .start_writer(rx, udp.send.clone())
                .await
                .context("Failed to start UDP writer")?;
        }
        config::TxTransport::Zenoh(zenoh) => {
            zenoh_transport
                .start_writer(rx, zenoh.key_pub.clone())
                .await
                .unwrap()
        }
    }
    Ok(())
}


#[async_trait]
pub trait AsyncTransport {
    type Config;
    type Error;

    async fn start_reader(
        &self,
        tx: Sender<Vec<u8>>,
        config: Self::Config,
    ) -> Result<(), Self::Error>;
    async fn start_writer(
        &self,
        mut rx: Receiver<Vec<u8>>,
        config: Self::Config,
    ) -> Result<(), Self::Error>;
}

// UDP Transport
pub struct UdpTransport;

#[derive(Error, Debug)]
pub enum UdpTransportError{
    #[error("Address parse error {0}")]
    AddrParseError(#[from] AddrParseError),
    #[error("IO error {0}")]
    IOError(#[from] io::Error)
}

#[async_trait]
impl AsyncTransport for UdpTransport {
    type Config = String;
    type Error = Error;

    async fn start_reader(&self, tx: Sender<Vec<u8>>, addr: String) -> Result<(), Self::Error> {
        let socket_addr = SocketAddr::from_str(&addr)?;
        let socket = UdpSocket::bind(socket_addr).await?;

        let mut buf = [0u8; TRANSPORT_BUFFER_SIZE];

        tokio::spawn(async move {
            while let Ok(sz) = socket.recv(&mut buf).await {
                if tx.send(buf[..sz].to_vec()).await.is_err() {
                    break;
                }
            }
        });

        Ok(())
    }

    async fn start_writer(
        &self,
        mut rx: Receiver<Vec<u8>>,
        addr: String,
    ) -> Result<(), Self::Error> {
        let socket = UdpSocket::bind("0.0.0.0:0").await?;

        let socket_addr = tokio::net::lookup_host(&addr).await?.into_iter().next();

        if socket_addr.is_none() {
            return Err(Error::msg("Failed to resolve address"));
        }

        socket.connect(socket_addr.unwrap()).await?;

        tokio::spawn(async move {
            while let Some(bytes) = rx.recv().await {
                if let Err(e) = socket.send(&bytes).await {
                    eprintln!("UDP send error: {}", e);
                    break;
                }
            }
        });

        Ok(())
    }
}

// Zenoh Transport
pub struct ZenohTransport {
    session: Session,
}

impl ZenohTransport {
    pub fn new(session: Session) -> Self {
        Self { session }
    }
}

#[async_trait]
impl AsyncTransport for ZenohTransport {
    type Config = String;
    type Error = zenoh::Error;

    async fn start_reader(&self, tx: Sender<Vec<u8>>, key: String) -> Result<(), Self::Error> {
        let key_expr = OwnedKeyExpr::try_from(key)?;
        let subscriber = self.session.declare_subscriber(key_expr).await?;

        tokio::spawn(async move {
            while let Ok(sample) = subscriber.recv_async().await {
                let bytes_vec = sample.payload().to_bytes().to_vec();
                if tx.send(bytes_vec).await.is_err() {
                    break;
                }
            }
        });

        Ok(())
    }

    async fn start_writer(
        &self,
        mut rx: Receiver<Vec<u8>>,
        key: String,
    ) -> Result<(), Self::Error> {
        let key_expr = OwnedKeyExpr::try_from(key)?;
        let publisher = self.session.declare_publisher(key_expr).await?;

        tokio::spawn(async move {
            while let Some(bytes) = rx.recv().await {
                if let Err(e) = publisher.put(bytes).wait() {
                    eprintln!("Zenoh publish error: {}", e);
                    break;
                }
            }
        });

        Ok(())
    }
}