use std::fs;
use std::path::Path;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: pll <command> [file]");
        eprintln!("Commands: check, compile, run, tokens, ast, codegen, multi-run, install, selfhost-compile, repl");
        return ExitCode::FAILURE;
    }
    let command = &args[1];
    let _file = args.get(2).map(|s| s.as_str()).unwrap_or("");
    match command.as_str() {
        "check" => cmd_check(_file),
        "run" => {
            if args.get(2).map(|s| s.as_str()) == Some("--bc") {
                cmd_run_bc(args.get(3).map(|s| s.as_str()).unwrap_or(""), args.get(4..).unwrap_or(&[]))
            } else {
                cmd_run(_file, args.get(3..).unwrap_or(&[]))
            }
        }
        "compile" => {
            if args.get(2).map(|s| s.as_str()) == Some("--bc") {
                cmd_compile_bc(args.get(3).map(|s| s.as_str()).unwrap_or(""))
            } else {
                cmd_compile(_file)
            }
        }
        "tokens" => cmd_tokens(_file),
        "ast" => cmd_ast(_file),
        "codegen" => cmd_codegen(_file),
        "multi-run" => cmd_multi_run(&args),
        "install" => cmd_install(_file),
        "selfhost-compile" => cmd_selfhost_compile(_file),
        "repl" => cmd_repl(),
        _ => { eprintln!("Unknown command"); ExitCode::FAILURE }
    }
}

fn read_source(file: &str) -> Result<String, String> {
    if file.is_empty() {
        let mut input = String::new();
        std::io::Read::read_to_string(&mut std::io::stdin(), &mut input)
            .map_err(|e| format!("Failed to read stdin: {}", e))?;
        Ok(input)
    } else {
        fs::read_to_string(file).map_err(|e| format!("Failed to read '{}': {}", file, e))
    }
}

fn lex(source: &str) -> Result<Vec<pll_core::Spanned<pll_core::Token>>, String> {
    let lexer = pll_lexer::Lexer::new(source);
    lexer.tokenize().map_err(|e| {
        if let Some(span) = &e.span { format!("Lex error at {}:{}: {}", span.start.line, span.start.column, e.message) }
        else { format!("Lex error: {}", e.message) }
    })
}

fn parse(source: &str) -> Result<pll_core::Program, String> {
    let tokens = lex(source)?;
    let mut parser = pll_parser::Parser::new(tokens);
    parser.parse_program().map_err(|e| {
        if let Some(span) = &e.span { format!("Parse error at {}:{}: {}", span.start.line, span.start.column, e.message) }
        else { format!("Parse error: {}", e.message) }
    })
}

fn type_check(program: &pll_core::Program) -> Result<(), String> {
    let mut env = pll_typeck::env::TypeEnv::new();
    env.check_program(program).map_err(|e| format!("Type error at {}:{}: {}", e.span.start.line, e.span.start.column, e.message))
}

fn cmd_tokens(file: &str) -> ExitCode {
    let source = match read_source(file) { Ok(s) => s, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    match lex(&source) {
        Ok(tokens) => { for tok in &tokens { println!("{}", tok.value.kind_name()); } ExitCode::SUCCESS }
        Err(e) => { eprintln!("{}", e); ExitCode::FAILURE }
    }
}

fn cmd_ast(file: &str) -> ExitCode {
    let source = match read_source(file) { Ok(s) => s, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    match parse(&source) { Ok(p) => { println!("{:#?}", p); ExitCode::SUCCESS } Err(e) => { eprintln!("{}", e); ExitCode::FAILURE } }
}

fn cmd_check(file: &str) -> ExitCode {
    let source = match read_source(file) { Ok(s) => s, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    match parse(&source) {
        Ok(program) => { match type_check(&program) { Ok(()) => { println!("OK — {} statement(s)", program.statements.len()); ExitCode::SUCCESS } Err(e) => { eprintln!("{}", e); ExitCode::FAILURE } } }
        Err(e) => { eprintln!("{}", e); ExitCode::FAILURE }
    }
}

fn cmd_codegen(file: &str) -> ExitCode {
    let source = match read_source(file) { Ok(s) => s, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    let program = match parse(&source) { Ok(p) => p, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    let _ = type_check(&program);
    let mut cg = pll_codegen::Codegen::new("pll_program");
    let output = cg.emit_program(&program);
    println!("{}", output);
    ExitCode::SUCCESS
}

fn cmd_compile(file: &str) -> ExitCode {
    let source = match read_source(file) { Ok(s) => s, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    let program = match parse(&source) { Ok(p) => p, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    let _ = type_check(&program);
    let out_dir = if file.is_empty() { "pll_out".to_string() } else {
        Path::new(file).file_stem().map(|s| format!("pll_{}", s.to_string_lossy())).unwrap_or_else(|| "pll_out".to_string())
    };
    let _ = fs::create_dir_all(&out_dir);
    let module_name = out_dir.trim_start_matches("pll_");
    let mut cg = pll_codegen::Codegen::new(module_name);
    let rust_code = cg.emit_program(&program);
    let _ = fs::create_dir_all(Path::new(&out_dir).join("src"));
    let main_rs = format!("{}\nfn main() {{ {}::run(); }}\n", rust_code, module_name);
    let _ = fs::write(Path::new(&out_dir).join("src").join("main.rs"), &main_rs);
    println!("Generated: {}/", out_dir);
    ExitCode::SUCCESS
}

fn cmd_compile_bc(file: &str) -> ExitCode {
    let source = match read_source(file) { Ok(s) => s, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    if file.is_empty() { eprintln!("No file specified"); return ExitCode::FAILURE; }
    let program = match parse(&source) { Ok(p) => p, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    let mut compiler = pll_bytecode::Compiler::new();
    compiler.compile_program(&program);
    let bc = compiler.into_bytecode();
    let pll_fmt = pll_bytecode::bc_to_pll_string(&bc);
    let out_path = format!("{}.bc.pll", file.trim_end_matches(".pll"));
    let output = format!("v _bc_prog != {}\nrun_bc(_bc_prog)\n", pll_fmt);
    let _ = fs::write(&out_path, &output);
    println!("Generated: {} ({} bytes)", out_path, bc.len());
    ExitCode::SUCCESS
}

fn cmd_run(file: &str, pll_args: &[String]) -> ExitCode {
    pll_runtime::set_args(pll_args.to_vec());
    let source = match read_source(file) { Ok(s) => s, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    let program = match parse(&source) { Ok(p) => p, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    if let Err(e) = type_check(&program) { eprintln!("{}", e); }
    let mut compiler = pll_bytecode::Compiler::new();
    compiler.compile_program(&program);
    let bc = compiler.into_bytecode();
    let mut env = pll_bytecode::BcEnv::new(bc);
    match env.run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => { eprintln!("Runtime error: {}", e); ExitCode::FAILURE }
    }
}

fn cmd_run_bc(file: &str, pll_args: &[String]) -> ExitCode {
    pll_runtime::set_args(pll_args.to_vec());
    let source = match read_source(file) { Ok(s) => s, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    let program = match parse(&source) { Ok(p) => p, Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; } };
    if let Err(e) = type_check(&program) { eprintln!("{}", e); }
    let mut compiler = pll_bytecode::Compiler::new();
    compiler.compile_program(&program);
    let bc = compiler.into_bytecode();
    let mut env = pll_bytecode::BcEnv::new(bc);
    match env.run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => { eprintln!("Runtime error: {}", e); ExitCode::FAILURE }
    }
}

fn cmd_repl() -> ExitCode {
    use std::io::{stdin, BufRead};
    eprintln!("PLL v2 REPL — type .exit to quit");
    let mut buffer = String::new();
    loop {
        eprint!("pll> ");
        let mut line = String::new();
        match stdin().lock().read_line(&mut line) { Ok(0) | Err(_) => break, Ok(_) => {} }
        let trimmed = line.trim();
        if trimmed == ".exit" || trimmed == ".quit" { break; }
        if trimmed.is_empty() || trimmed.starts_with('#') { continue; }
        buffer.push_str(&line);
        match parse(&buffer) {
            Ok(program) => {
                let mut compiler = pll_bytecode::Compiler::new();
                compiler.compile_program(&program);
                let mut env = pll_bytecode::BcEnv::new(compiler.into_bytecode());
                if let Err(e) = env.run() { eprintln!("Error: {}", e); }
                buffer.clear();
            }
            Err(e) => { if e.contains("end of file") { continue; } eprintln!("{}", e); buffer.clear(); }
        }
    }
    ExitCode::SUCCESS
}

fn cmd_selfhost_compile(_file: &str) -> ExitCode {
    eprintln!("selfhost-compile: use cargo build --release -p pll-cli instead");
    ExitCode::FAILURE
}

fn cmd_multi_run(_args: &[String]) -> ExitCode {
    eprintln!("multi-run: build with cargo build --release -p pll-cli and run the resulting binary");
    ExitCode::FAILURE
}

fn cmd_install(_path: &str) -> ExitCode {
    eprintln!("install: not supported in this build");
    ExitCode::FAILURE
}
