use std::sync::mpsc;

pub trait Transport: Send {
    fn send(&mut self, msg: &str);
    fn recv(&mut self) -> Option<String>;
}

pub struct PipeTransport {
    sender: mpsc::Sender<String>,
    receiver: mpsc::Receiver<String>,
    buffer: Option<String>,
}

impl PipeTransport {
    pub fn new() -> (Self, Self) {
        let (tx_a, rx_a) = mpsc::channel();
        let (tx_b, rx_b) = mpsc::channel();
        (PipeTransport { sender: tx_a, receiver: rx_b, buffer: None },
         PipeTransport { sender: tx_b, receiver: rx_a, buffer: None })
    }
}

impl Transport for PipeTransport {
    fn send(&mut self, msg: &str) {
        let _ = self.sender.send(msg.to_string());
    }
    fn recv(&mut self) -> Option<String> {
        if let Some(msg) = self.buffer.take() { return Some(msg); }
        self.receiver.try_recv().ok()
    }
}

pub struct PairedTransport {
    pub a: PipeTransport,
    pub b: PipeTransport,
}

impl PairedTransport {
    pub fn new() -> Self {
        let (a, b) = PipeTransport::new();
        PairedTransport { a, b }
    }
    pub fn route_a_to_b(&mut self) {
        let temp = std::mem::replace(&mut self.a, PipeTransport::new().0);
        self.a = temp;
    }
    pub fn route_b_to_a(&mut self) {
        let temp = std::mem::replace(&mut self.b, PipeTransport::new().0);
        self.b = temp;
    }
}
