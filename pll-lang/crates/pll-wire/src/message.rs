use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Envelope {
    pub version: u8,
    pub msg_type: MsgType,
    pub payload: String,
    pub sender: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MsgType {
    Hello, Ack, Schema, Data, Error,
}
