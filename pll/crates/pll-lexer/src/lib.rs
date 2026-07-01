use pll_core::*;

pub struct Lexer {
    chars: Vec<char>,
    pos: usize,
    line: usize,
    col: usize,
}

#[derive(Debug)]
pub struct LexError {
    pub message: String,
    pub span: Option<Span>,
}

impl Lexer {
    pub fn new(source: &str) -> Self {
        Self { chars: source.chars().collect(), pos: 0, line: 1, col: 1 }
    }

    pub fn tokenize(&self) -> Result<Vec<Spanned<Token>>, LexError> {
        let mut tokens = Vec::new();
        let mut pos = 0;
        let mut line = 1;
        let mut col = 1;
        let chars = &self.chars;
        let len = chars.len();

        while pos < len {
            let start_line = line;
            let start_col = col;

            if chars[pos] == '#' {
                while pos < len && chars[pos] != '\n' { pos += 1; col += 1; }
                continue;
            }
            if chars[pos] == '\n' {
                tokens.push(Spanned {
                    value: Token::Newline,
                    span: Span { start: Position { line, column: col, offset: pos as u32 }, end: Position { line, column: col + 1, offset: pos as u32 + 1 } },
                });
                pos += 1; line += 1; col = 1;
                continue;
            }
            if chars[pos].is_whitespace() { pos += 1; col += 1; continue; }

            let start_pos = pos;
            let tok = match chars[pos] {
                '+' => { pos += 1; col += 1; Token::Plus }
                '-' => {
                    pos += 1; col += 1;
                    if pos < len && chars[pos] == '>' { pos += 1; col += 1; Token::Arrow }
                    else { Token::Minus }
                }
                '*' => { pos += 1; col += 1; Token::Star }
                '/' => { pos += 1; col += 1; Token::Slash }
                '%' => { pos += 1; col += 1; Token::Percent }
                '(' => { pos += 1; col += 1; Token::LParen }
                ')' => { pos += 1; col += 1; Token::RParen }
                '{' => { pos += 1; col += 1; Token::LBrace }
                '}' => { pos += 1; col += 1; Token::RBrace }
                '[' => { pos += 1; col += 1; Token::LBracket }
                ']' => { pos += 1; col += 1; Token::RBracket }
                ',' => { pos += 1; col += 1; Token::Comma }
                '.' => { pos += 1; col += 1; Token::Dot }
                ':' => { pos += 1; col += 1; Token::Colon }
                '!' => {
                    pos += 1; col += 1;
                    if pos < len && chars[pos] == '=' { pos += 1; col += 1; Token::Neq }
                    else { return Err(LexError { message: "Expected '=' after '!'".into(), span: None }); }
                }
                '=' => {
                    pos += 1; col += 1;
                    if pos < len && chars[pos] == '=' { pos += 1; col += 1; Token::Eq }
                    else if pos < len && chars[pos] == '>' { pos += 1; col += 1; Token::FatArrow }
                    else { Token::Assign }
                }
                '>' => { pos += 1; col += 1; if pos < len && chars[pos] == '=' { pos += 1; col += 1; Token::Gte } else { Token::Gt } }
                '<' => { pos += 1; col += 1; if pos < len && chars[pos] == '=' { pos += 1; col += 1; Token::Lte } else { Token::Lt } }
                '&' => { pos += 1; col += 1; if pos < len && chars[pos] == '&' { pos += 1; col += 1; Token::And } else { return Err(LexError { message: "Expected '&'".into(), span: None }); } }
                '|' => { pos += 1; col += 1; if pos < len && chars[pos] == '|' { pos += 1; col += 1; Token::Or } else { return Err(LexError { message: "Expected '|'".into(), span: None }); } }
                '~' => {
                    pos += 1; col += 1;
                    if pos < len && chars[pos] == '>' { pos += 1; col += 1; Token::FatArrow } else { Token::Minus }
                }
                '`' => {
                    pos += 1; col += 1;
                    let start = pos;
                    while pos < len && chars[pos] != '`' { pos += 1; col += 1; }
                    let s: String = chars[start..pos].iter().collect();
                    pos += 1; col += 1;
                    Token::MetaStart
                }
                '"' => {
                    pos += 1; col += 1;
                    let start = pos;
                    while pos < len && chars[pos] != '"' {
                        if chars[pos] == '\\' { pos += 1; col += 1; }
                        pos += 1; col += 1;
                    }
                    let s: String = chars[start..pos].iter().collect();
                    pos += 1; col += 1;
                    Token::Str(s)
                }
                _ if chars[pos].is_ascii_digit() || (chars[pos] == '.' && pos + 1 < len && chars[pos + 1].is_ascii_digit()) => {
                    let start = pos;
                    let mut is_float = false;
                    while pos < len && (chars[pos].is_ascii_digit() || chars[pos] == '.') {
                        if chars[pos] == '.' { is_float = true; }
                        pos += 1; col += 1;
                    }
                    let s: String = chars[start..pos].iter().collect();
                    let n: f64 = s.parse().unwrap_or(0.0);
                    Token::Num(n)
                }
                _ if chars[pos].is_alphabetic() || chars[pos] == '_' || chars[pos] == '?' => {
                    let start = pos;
                    while pos < len && (chars[pos].is_alphanumeric() || chars[pos] == '_') { pos += 1; col += 1; }
                    let s: String = chars[start..pos].iter().collect();
                    match s.as_str() {
                        "fn" => Token::Fn, "return" => Token::Return,
                        "if" => Token::If, "else" => Token::Else,
                        "while" => Token::While, "foreach" => Token::ForEach,
                        "in" => Token::In, "import" => Token::Import,
                        "v" => Token::V, "render" => Token::Render,
                        "emit" => Token::Emit, "send" => Token::Send,
                        "recv" => Token::Recv, "print" => Token::Print,
                        "t" => Token::T, "p" => Token::P,
                        "agent" => Token::Agent, "on" => Token::On,
                        "cap" => Token::Cap, "contract" => Token::Contract,
                        "ui" => Token::Ui, "route" => Token::Route,
                        "par" => Token::Par, "join" => Token::Join,
                        "fork" => Token::Fork, "converge" => Token::Converge,
                        "str" => Token::TypeStr, "num" => Token::TypeNum,
                        "bool" => Token::TypeBool, "list" => Token::TypeList,
                        "record" => Token::TypeRecord, "event" => Token::TypeEvent,
                        "true" => Token::Bool(true), "false" => Token::Bool(false),
                        _ => Token::Ident(s),
                    }
                }
                _ => return Err(LexError {
                    message: format!("Unexpected character: '{}'", chars[pos]),
                    span: Some(Span { start: Position { line, column: col, offset: pos as u32 }, end: Position { line, column: col + 1, offset: pos as u32 + 1 } }),
                }),
            };
            let end_pos = pos;
            tokens.push(Spanned {
                value: tok,
                span: Span {
                    start: Position { line: start_line, column: start_col, offset: start_pos as u32 },
                    end: Position { line, column: col, offset: end_pos as u32 },
                },
            });
        }
        tokens.push(Spanned {
            value: Token::End,
            span: Span { start: Position { line, column: col, offset: pos as u32 }, end: Position { line, column: col, offset: pos as u32 } },
        });
        Ok(tokens)
    }
}

impl std::fmt::Display for LexError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}
