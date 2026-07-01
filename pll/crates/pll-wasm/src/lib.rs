use std::collections::HashMap;
use std::sync::Mutex;

static VFS: Mutex<HashMap<String, String>> = Mutex::new(HashMap::new());

pub fn set_virtual_file(path: &str, content: &str) {
    if let Ok(mut vfs) = VFS.lock() {
        if content.is_empty() { vfs.remove(path); }
        else { vfs.insert(path.to_string(), content.to_string()); }
    }
}

pub fn get_virtual_file(path: &str) -> Option<String> {
    VFS.lock().ok().and_then(|vfs| vfs.get(path).cloned())
}

pub fn compile_and_run(filename: &str) -> String {
    let source = match get_virtual_file(filename) {
        Some(s) => s, None => return format!("File not found: {}", filename),
    };
    let tokens = match pll_lexer::Lexer::new(&source).tokenize() {
        Ok(t) => t, Err(e) => return format!("Lex error: {}", e),
    };
    let program = match pll_parser::Parser::new(tokens).parse_program() {
        Ok(p) => p, Err(e) => return format!("Parse error: {}", e),
    };
    let output = std::sync::Mutex::new(String::new());
    // Run via pll_vm
    let mut env = pll_vm::Environment::new();
    match pll_vm::run_program(&program, &mut env) {
        Ok(()) => pll_runtime::last_rendered().unwrap_or_default(),
        Err(e) => format!("Runtime error: {}", e),
    }
}
