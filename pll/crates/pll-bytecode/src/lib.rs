mod opcodes;
mod compiler;
mod vm;
mod fmt;

pub use opcodes::*;
pub use compiler::Compiler;
pub use compiler::FnInfo;
pub use vm::BcEnv;
pub use vm::BcValue;
pub use vm::BUILTIN_RENDER;
pub use vm::BUILTIN_PRINT;
pub use vm::BUILTIN_EMIT;
pub use vm::BUILTIN_STR_CONCAT;
pub use vm::BUILTIN_STR_LENGTH;
pub use vm::BUILTIN_STR_SLICE;
pub use vm::BUILTIN_STR_CHAR_AT;
pub use vm::BUILTIN_STR_TO_NUM;
pub use vm::BUILTIN_STR_FROM_NUM;
pub use vm::BUILTIN_STR_STARTS_WITH;
pub use vm::BUILTIN_STR_TO_UPPER;
pub use vm::BUILTIN_LIST_LENGTH;
pub use vm::BUILTIN_LIST_GET;
pub use vm::BUILTIN_LIST_PUSH;
pub use vm::BUILTIN_READ_FILE;
pub use vm::BUILTIN_WRITE_FILE;
pub use vm::BUILTIN_DB_SET;
pub use vm::BUILTIN_DB_GET;
pub use fmt::*;

#[cfg(test)]
mod tests {
    use super::*;

    fn compile(source: &str) -> Vec<u8> {
        let tokens = pll_lexer::Lexer::new(source).tokenize().unwrap();
        let program = pll_parser::Parser::new(tokens).parse_program().unwrap();
        let mut c = Compiler::new();
        c.compile_program(&program);
        c.into_bytecode()
    }

    fn run(source: &str) -> Result<(), String> {
        let bc = compile(source);
        let mut env = BcEnv::new(bc);
        env.run()
    }

    fn run_and_capture(source: &str) -> String {
        use std::io::Write;
        pll_runtime::pll_render("");
        let _ = std::io::stdout().flush();
        let bc = compile(source);
        let mut env = BcEnv::new(bc);
        let _ = env.run();
        pll_runtime::last_rendered().unwrap_or_default()
    }

    #[test]
    fn test_push_num() {
        let mut bc = Vec::new();
        bc.extend_from_slice(&[0; 4]); // offset header (no FnTable)
        bc.push(Opcode::PushNum as u8);
        bc.extend_from_slice(&42.0f64.to_le_bytes());
        bc.push(Opcode::Halt as u8);
        let mut env = BcEnv::new(bc);
        env.run().unwrap();
        let val = env.pop();
        assert!((val.as_num().unwrap() - 42.0).abs() < 1e-10);
    }

    #[test]
    fn test_add() {
        let mut bc = Vec::new();
        bc.extend_from_slice(&[0; 4]);
        bc.push(Opcode::PushNum as u8);
        bc.extend_from_slice(&10.0f64.to_le_bytes());
        bc.push(Opcode::PushNum as u8);
        bc.extend_from_slice(&20.0f64.to_le_bytes());
        bc.push(Opcode::Add as u8);
        bc.push(Opcode::Halt as u8);
        let mut env = BcEnv::new(bc);
        env.run().unwrap();
        assert!((env.pop().as_num().unwrap() - 30.0).abs() < 1e-10);
    }

    #[test]
    fn test_render_42() {
        assert_eq!(run_and_capture("render 42"), "42");
    }

    #[test]
    fn test_variable() {
        assert_eq!(run_and_capture("v x != 42\nrender x"), "42");
    }

    #[test]
    fn test_arithmetic() {
        assert_eq!(run_and_capture("v x != 1 + 2 * 3\nrender x"), "7");
    }

    #[test]
    fn test_comparison_lt() {
        assert_eq!(run_and_capture("v r != 0 < 1\nrender r"), "true");
    }

    #[test]
    fn test_comparison_gt() {
        assert_eq!(run_and_capture("v r != 2 > 1\nrender r"), "true");
    }

    #[test]
    fn test_if_true() {
        assert_eq!(run_and_capture("if 1:\n    render 42\nelse:\n    render 0"), "42");
    }

    #[test]
    fn test_if_false() {
        assert_eq!(run_and_capture("if 0:\n    render 42\nelse:\n    render 0"), "0");
    }

    #[test]
    fn test_while_loop() {
        let result = run_and_capture("v i != 0\nwhile i < 3:\n    render i\n    i != i + 1");
        assert_eq!(result, "2"); // last_rendered returns only the last value
    }

    #[test]
    fn test_function_call() {
        let result = run_and_capture(
            "fn double(n: num) -> num:\n    return n * 2\n\nv x != double(21)\nrender x"
        );
        assert_eq!(result, "42");
    }

    #[test]
    fn test_string_concat() {
        let result = run_and_capture("render str_concat(\"hello\", \" world\")");
        assert_eq!(result, "hello world");
    }

    #[test]
    fn test_record() {
        let result = run_and_capture("v user != {}\nrender user");
        assert_eq!(result, "{}");
    }

    #[test]
    fn test_list() {
        let result = run_and_capture("v items != []\nrender items");
        assert_eq!(result, "[]");
    }

    #[test]
    fn test_nested_if_else() {
        let result = run_and_capture(
            "v x != 10\nif x > 5:\n    if x > 8:\n        render 1\n    else:\n        render 0\nelse:\n    render 0"
        );
        assert_eq!(result, "1");
    }

    #[test]
    fn test_recursive_function() {
        let result = run_and_capture(
            "fn fact(n: num) -> num:\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\n\nv r != fact(3)\nrender r"
        );
        assert_eq!(result, "6");
    }

    #[test]
    fn test_factorial() {
        let result = run_and_capture("v r != 1*2*3*4*5\nrender r");
        assert_eq!(result, "120");
    }

    #[test]
    fn test_multiple_renders() {
        let result = run_and_capture("render 1\nrender 2\nrender 3");
        assert_eq!(result, "3"); // last_rendered returns only the last value
    }

    #[test]
    fn test_complex_expression() {
        let result = run_and_capture("v x != (1 + 2) * (3 + 4)\nrender x");
        assert_eq!(result, "21");
    }

}

