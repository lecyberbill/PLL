use std::collections::HashMap;
use std::sync::Mutex;
use wasm_bindgen::prelude::*;

use std::sync::LazyLock;

static VFS: LazyLock<Mutex<HashMap<String, String>>> = LazyLock::new(|| Mutex::new(HashMap::new()));

#[wasm_bindgen]
pub fn set_virtual_file(path: &str, content: &str) {
    if let Ok(mut vfs) = VFS.lock() {
        if content.is_empty() {
            vfs.remove(path);
        } else {
            vfs.insert(path.to_string(), content.to_string());
        }
    }
}

#[wasm_bindgen]
pub fn get_virtual_file(path: &str) -> Option<String> {
    VFS.lock().ok().and_then(|vfs| vfs.get(path).cloned())
}

#[wasm_bindgen]
pub fn compile_and_run(filename: &str) -> String {
    let source = match get_virtual_file(filename) {
        Some(s) => s,
        None => return format!("File not found: {}", filename),
    };
    let tokens = match pll_lexer::Lexer::new(&source).tokenize() {
        Ok(t) => t,
        Err(e) => return format!("Lex error: {}", e),
    };
    let program = match pll_parser::Parser::new(tokens).parse_program() {
        Ok(p) => p,
        Err(e) => return format!("Parse error: {}", e),
    };
    
    // Compile using pll-bytecode compiler
    let mut compiler = pll_bytecode::Compiler::new();
    compiler.compile_program(&program);
    let bc = compiler.into_bytecode();
    
    // Run using pll-bytecode VM
    let mut env = pll_bytecode::BcEnv::new(bc);
    match env.run() {
        Ok(()) => pll_runtime::last_rendered().unwrap_or_default(),
        Err(e) => format!("Runtime error: {}", e),
    }
}

#[wasm_bindgen]
pub fn compile_to_bytecode_string(filename: &str) -> String {
    let source = match get_virtual_file(filename) {
        Some(s) => s,
        None => return format!("File not found: {}", filename),
    };
    let tokens = match pll_lexer::Lexer::new(&source).tokenize() {
        Ok(t) => t,
        Err(e) => return format!("Lex error: {}", e),
    };
    let program = match pll_parser::Parser::new(tokens).parse_program() {
        Ok(p) => p,
        Err(e) => return format!("Parse error: {}", e),
    };
    
    let mut compiler = pll_bytecode::Compiler::new();
    compiler.compile_program(&program);
    let bc = compiler.into_bytecode();
    pll_bytecode::bc_to_pll_string(&bc)
}
