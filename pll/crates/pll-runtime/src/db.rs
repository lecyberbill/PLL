use std::collections::HashMap;
use std::sync::Mutex;

static DB: Mutex<HashMap<String, String>> = Mutex::new(HashMap::new());

pub fn pll_db_set(key: String, value: String) {
    if let Ok(mut db) = DB.lock() { db.insert(key, value); }
}

pub fn pll_db_get(key: &str) -> Option<String> {
    DB.lock().ok().and_then(|db| db.get(key).cloned())
}

pub fn pll_db_keys() -> Vec<String> {
    DB.lock().ok().map(|db| db.keys().cloned().collect()).unwrap_or_default()
}
