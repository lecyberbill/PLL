use std::sync::{LazyLock, Mutex};
use std::io::Write;

static LAST_RENDER: Mutex<Option<String>> = Mutex::new(None);
pub static WASM_LOGS: LazyLock<Mutex<Vec<String>>> = LazyLock::new(|| Mutex::new(Vec::new()));
static ARGS: LazyLock<Mutex<Vec<String>>> = LazyLock::new(|| Mutex::new(Vec::new()));

thread_local! {
    static TRANSPORT: std::cell::RefCell<Option<Box<dyn std::any::Any + Send>>> = std::cell::RefCell::new(None) ;
}

pub fn set_args(args: Vec<String>) {
    *ARGS.lock().unwrap() = args;
}

pub fn pll_args() -> Vec<String> {
    ARGS.lock().unwrap().clone()
}

pub fn pll_render(value: &str) {
    #[cfg(not(target_arch = "wasm32"))]
    { println!("{}", value); let _ = std::io::stdout().flush(); }
    #[cfg(target_arch = "wasm32")]
    { if let Ok(mut logs) = WASM_LOGS.lock() { logs.push(value.to_string()); } }
    if let Ok(mut r) = LAST_RENDER.lock() { *r = Some(value.to_string()); }
}

pub fn last_rendered() -> Option<String> {
    LAST_RENDER.lock().ok().and_then(|r| r.clone())
}

pub fn pll_print(value: &str) {
    #[cfg(not(target_arch = "wasm32"))]
    { println!("{}", value); let _ = std::io::stdout().flush(); }
    #[cfg(target_arch = "wasm32")]
    { if let Ok(mut logs) = WASM_LOGS.lock() { logs.push(value.to_string()); } }
}

pub fn pll_emit(value: &str) {
    if let Ok(mut r) = LAST_RENDER.lock() { *r = Some(value.to_string()); }
}

pub fn pll_verify(condition: bool) {
    assert!(condition, "PLL verify failed");
}

pub fn pll_in(s: &str, list: &str) -> bool {
    list.contains(s)
}

pub fn pll_semantic_invert(s: &str) -> String {
    format!("not({})", s)
}

pub fn set_transport(transport: Box<dyn std::any::Any + Send>) {
    TRANSPORT.with(|t| { *t.borrow_mut() = Some(transport); });
}

pub fn take_transport() -> Option<Box<dyn std::any::Any + Send>> {
    TRANSPORT.with(|t| t.borrow_mut().take())
}

pub fn pll_send(_payload: &str) {}

pub fn pll_recv() -> String {
    String::new()
}

pub fn pll_send_raw(msg: &str) { pll_send(msg); }
pub fn pll_recv_raw() -> String { pll_recv() }
