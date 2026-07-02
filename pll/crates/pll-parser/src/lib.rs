use pll_core::*;

pub struct Parser {
    tokens: Vec<Spanned<Token>>,
    pos: usize,
}

#[derive(Debug)]
pub struct ParseError {
    pub message: String,
    pub span: Option<Span>,
}

impl Parser {
    pub fn new(tokens: Vec<Spanned<Token>>) -> Self {
        Self { tokens, pos: 0 }
    }

    fn peek(&self) -> &Token { &self.tokens[self.pos].value }
    fn peek_span(&self) -> &Span { &self.tokens[self.pos].span }
    fn advance(&mut self) -> &Token { let t = &self.tokens[self.pos]; self.pos += 1; &t.value }
    fn expect(&mut self, tok: &Token, msg: &str) -> Result<(), ParseError> {
        if std::mem::discriminant(self.peek()) == std::mem::discriminant(tok) {
            self.advance(); Ok(())
        } else {
            Err(ParseError { message: format!("{}: expected {:?}, got {:?}", msg, tok, self.peek()), span: Some(self.peek_span().clone()) })
        }
    }
    fn skip_newlines(&mut self) {
        while matches!(self.peek(), Token::Newline) { self.advance(); }
    }

    pub fn parse_program(&mut self) -> Result<Program, ParseError> {
        let mut stmts = Vec::new();
        self.skip_newlines();
        while !matches!(self.peek(), Token::End) {
            stmts.push(self.parse_stmt()?);
            self.skip_newlines();
        }
        Ok(Program {
            header: ProgramMeta { zone: "main".into(), lambda: 0.7, agent_id: None },
            statements: stmts,
        })
    }

    fn parse_stmt(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        self.skip_newlines();
        let token = self.peek().clone();
        let span = self.peek_span().clone();
        match &token {
            Token::V => self.parse_var_decl(),
            Token::Fn => self.parse_fn_decl(),
            Token::T => self.parse_type_decl(),
            Token::P => self.parse_protocol_decl(),
            Token::Agent => self.parse_agent_decl(),
            Token::Cap => self.parse_cap_decl(),
            Token::Contract => self.parse_contract_decl(),
            Token::If => self.parse_if(),
            Token::While => self.parse_while(),
            Token::ForEach => self.parse_for_each(),
            Token::Return => self.parse_return(),
            Token::Import => self.parse_import(),
            Token::Render => self.parse_render(),
            Token::Emit => self.parse_emit(),
            Token::Send => self.parse_send(),
            Token::Print => self.parse_print(),
            Token::Ui => self.parse_ui(),
            Token::Par => self.parse_par(),
            Token::Fork => self.parse_fork(),
            Token::Converge => self.parse_converge(),
            Token::MetaStart => self.parse_meta_exec(),
            Token::Ident(_) => self.parse_assignment_or_expr(),
            _ => Err(ParseError { message: format!("Unexpected token: {:?}", token), span: Some(span) }),
        }
    }

    fn parse_var_decl(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        self.advance();
        let name = if let Token::Ident(n) = &self.peek() { let n = n.clone(); self.advance(); n }
        else { return Err(ParseError { message: "Expected identifier after 'v'".into(), span: Some(self.peek_span().clone()) }); };
        self.expect(&Token::Assign, "Expected '!=' after variable name")?;
        let init = Some(self.parse_expr(0)?);
        Ok(Spanned { value: Stmt::VarDecl(VarDecl { name, raw_text: None, init, provenance: None }), span })
    }

    fn parse_fn_decl(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        self.advance();
        let name = if let Token::Ident(n) = &self.peek() { let n = n.clone(); self.advance(); n }
        else { return Err(ParseError { message: "Expected function name".into(), span: Some(self.peek_span().clone()) }); };
        self.expect(&Token::LParen, "Expected '('")?;
        let mut params = Vec::new();
        while !matches!(self.peek(), Token::RParen) {
            let pname = if let Token::Ident(n) = &self.peek() { let n = n.clone(); self.advance(); n }
            else { return Err(ParseError { message: "Expected parameter name".into(), span: Some(self.peek_span().clone()) }); };
            let mut typ = TypeRef::Any;
            if matches!(self.peek(), Token::Colon) {
                self.advance();
                typ = self.parse_type_ref()?;
            }
            params.push(Field { name: pname, type_ref: typ, optional: false });
            if matches!(self.peek(), Token::Comma) { self.advance(); }
        }
        self.expect(&Token::RParen, "Expected ')'")?;
        let mut ret_type = TypeRef::Any;
        if matches!(self.peek(), Token::Arrow) { self.advance(); ret_type = self.parse_type_ref()?; }
        self.expect(&Token::Colon, "Expected ':' after function signature")?;
        let body = self.parse_block("fn")?;
        Ok(Spanned { value: Stmt::FnDecl(FnDecl { name, params, ret_type, body }), span })
    }

    fn parse_type_decl(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        self.advance();
        let name = if let Token::Ident(n) = &self.peek() { let n = n.clone(); self.advance(); n }
        else { return Err(ParseError { message: "Expected type name".into(), span: Some(self.peek_span().clone()) }); };
        self.expect(&Token::LBracket, "Expected '['")?;
        let mut fields = Vec::new();
        while !matches!(self.peek(), Token::RBracket) {
            let fname = if let Token::Ident(n) = &self.peek() { let n = n.clone(); self.advance(); n }
            else { return Err(ParseError { message: "Expected field name".into(), span: Some(self.peek_span().clone()) }); };
            let mut typ = TypeRef::Any;
            if matches!(self.peek(), Token::Colon) { self.advance(); typ = self.parse_type_ref()?; }
            let optional = matches!(self.peek(), Token::Ident(_)) && matches!(self.tokens.get(self.pos + 1).map(|t| &t.value), Some(Token::RBracket) | Some(Token::Comma));
            fields.push(Field { name: fname, type_ref: typ, optional });
            if matches!(self.peek(), Token::Comma) { self.advance(); }
            self.skip_newlines();
        }
        self.expect(&Token::RBracket, "Expected ']'")?;
        Ok(Spanned { value: Stmt::TypeDecl(TypeDecl { name, fields }), span })
    }

    fn parse_if(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        self.advance();
        let condition = self.parse_expr(0)?;
        self.expect(&Token::Colon, "Expected ':' after if condition")?;
        let then_body = self.parse_block("if")?;
        let mut else_body = None;
        if matches!(self.peek(), Token::Else) {
            self.advance();
            if matches!(self.peek(), Token::If) { return self.parse_if(); }
            self.expect(&Token::Colon, "Expected ':' after else")?;
            else_body = Some(self.parse_block("else")?);
        }
        Ok(Spanned { value: Stmt::If(If { condition, then_body, else_body }), span })
    }

    fn parse_while(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        self.advance();
        let condition = self.parse_expr(0)?;
        self.expect(&Token::Colon, "Expected ':'")?;
        let body = self.parse_block("while")?;
        Ok(Spanned { value: Stmt::While(While { condition, body }), span })
    }

    fn parse_for_each(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        self.advance();
        let var = match self.peek() {
            Token::Ident(n) => { let n = n.clone(); self.advance(); n }
            Token::V => { self.advance(); "v".to_string() }
            _ => return Err(ParseError { message: "Expected variable name".into(), span: Some(self.peek_span().clone()) }),
        };
        self.expect(&Token::In, "Expected 'in'")?;
        let iter = self.parse_expr(0)?;
        self.expect(&Token::Colon, "Expected ':'")?;
        let body = self.parse_block("foreach")?;
        Ok(Spanned { value: Stmt::ForEach(ForEach { var, iter, body }), span })
    }

    fn parse_return(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        self.advance();
        let value = self.parse_expr(0)?;
        Ok(Spanned { value: Stmt::Return(value), span })
    }

    fn parse_import(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        self.advance();
        let path = if let Token::Str(s) = &self.peek() { let s = s.clone(); self.advance(); s }
        else if let Token::Ident(s) = &self.peek() { let s = s.clone(); self.advance(); s }
        else { return Err(ParseError { message: "Expected import path".into(), span: Some(self.peek_span().clone()) }); };
        Ok(Spanned { value: Stmt::Import(path), span })
    }

    fn parse_render(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::Render(self.parse_expr(0)?), span })
    }
    fn parse_emit(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::Emit(self.parse_expr(0)?), span })
    }
    fn parse_send(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::Send(self.parse_expr(0)?), span })
    }
    fn parse_print(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::Print(self.parse_expr(0)?), span })
    }

    fn parse_ui(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        let content = if let Token::Str(s) = &self.peek() { let s = s.clone(); self.advance(); s }
        else { return Err(ParseError { message: "Expected string".into(), span: Some(self.peek_span().clone()) }); };
        Ok(Spanned { value: Stmt::Ui(content), span })
    }

    fn parse_par(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        self.expect(&Token::Colon, "Expected ':'")?;
        let mut branches = Vec::new();
        while !matches!(self.peek(), Token::End) && !matches!(self.peek(), Token::Join) {
            let block = self.parse_block("par")?;
            branches.push(block);
        }
        if matches!(self.peek(), Token::Join) { self.advance(); let _ = self.peek().clone(); }
        Ok(Spanned { value: Stmt::Par(branches), span })
    }

    fn parse_fork(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        let mut branches = Vec::new();
        self.skip_newlines();
        while !matches!(self.peek(), Token::End) && !matches!(self.peek(), Token::Newline) {
            if matches!(self.peek(), Token::Else) { break; }
            if let Token::Str(s) = &self.peek() { let label = s.clone(); self.advance(); branches.push(ForkBranch { condition: label, confidence: 0.0, body: self.parse_block("fork")? }); }
            else { break; }
        }
        Ok(Spanned { value: Stmt::Fork(branches), span })
    }

    fn parse_converge(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::Converge(Converge { target: 0.9, patience: 2, max_steps: 3, strategies: vec![], conditions: vec![] }), span })
    }

    fn parse_meta_exec(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::MetaExec(self.parse_expr(0)?), span })
    }

    fn parse_assignment_or_expr(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone();
        let name = if let Token::Ident(n) = &self.peek() { let n = n.clone(); self.advance(); n }
        else { return Err(ParseError { message: "Expected identifier".into(), span: Some(span) }); };
        if matches!(self.peek(), Token::Assign) {
            self.advance();
            let value = self.parse_expr(0)?;
            Ok(Spanned { value: Stmt::Assign { name, value }, span })
        } else {
            // Rewind and parse as expression
            self.pos -= 1;
            let expr = self.parse_expr(0)?;
            Ok(Spanned { value: Stmt::Expr(expr), span })
        }
    }

    fn parse_type_ref(&mut self) -> Result<TypeRef, ParseError> {
        match self.peek() {
            Token::TypeStr => { self.advance(); Ok(TypeRef::Str) }
            Token::TypeNum => { self.advance(); Ok(TypeRef::Num) }
            Token::TypeBool => { self.advance(); Ok(TypeRef::Bool) }
            Token::TypeList => { self.advance(); Ok(TypeRef::List(Box::new(TypeRef::Any))) }
            Token::TypeRecord => { self.advance(); Ok(TypeRef::Any) }
            Token::TypeEvent => { self.advance(); Ok(TypeRef::Event) }
            Token::Ident(n) => { let n = n.clone(); self.advance(); Ok(TypeRef::Named(n)) }
            _ => Err(ParseError { message: "Expected type".into(), span: Some(self.peek_span().clone()) }),
        }
    }

    fn parse_expr(&mut self, _min_prec: u8) -> Result<Spanned<Expr>, ParseError> {
        self.parse_binary(0)
    }

    fn parse_binary(&mut self, min_prec: u8) -> Result<Spanned<Expr>, ParseError> {
        let mut left = self.parse_primary()?;
        while let Some((prec, op)) = self.binary_op_precedence() {
            if prec < min_prec { break; }
            self.advance();
            let right = self.parse_binary(prec + 1)?;
            let span = left.span.clone();
            left = Spanned {
                value: Expr::Binary(op, Box::new(left), Box::new(right)),
                span,
            };
        }
        Ok(left)
    }

    fn binary_op_precedence(&self) -> Option<(u8, BinaryOp)> {
        match self.peek() {
            Token::Or => Some((1, BinaryOp::Or)),
            Token::And => Some((2, BinaryOp::And)),
            Token::Eq => Some((3, BinaryOp::Eq)),
            Token::Neq => Some((3, BinaryOp::Neq)),
            Token::Gt => Some((4, BinaryOp::Gt)),
            Token::Lt => Some((4, BinaryOp::Lt)),
            Token::Gte => Some((4, BinaryOp::Gte)),
            Token::Lte => Some((4, BinaryOp::Lte)),
            Token::Plus => Some((5, BinaryOp::Add)),
            Token::Minus => Some((5, BinaryOp::Sub)),
            Token::Star => Some((6, BinaryOp::Mul)),
            Token::Slash => Some((6, BinaryOp::Div)),
            Token::Percent => Some((6, BinaryOp::Mod)),
            _ => None,
        }
    }

    fn parse_primary(&mut self) -> Result<Spanned<Expr>, ParseError> {
        let span = self.peek_span().clone();
        match self.peek() {
            Token::Num(n) => { let n = *n; self.advance(); Ok(Spanned { value: Expr::Literal(Literal::Num(n)), span }) }
            Token::Str(s) => { let s = s.clone(); self.advance(); Ok(Spanned { value: Expr::Literal(Literal::Str(s)), span }) }
            Token::Bool(b) => { let b = *b; self.advance(); Ok(Spanned { value: Expr::Literal(Literal::Bool(b)), span }) }
            Token::LParen => {
                self.advance();
                let expr = self.parse_expr(0)?;
                self.expect(&Token::RParen, "Expected ')'")?;
                Ok(expr)
            }
            Token::Ident(name) => {
                let name = name.clone(); self.advance();
                if matches!(self.peek(), Token::LParen) {
                    self.advance();
                    let mut args = Vec::new();
                    while !matches!(self.peek(), Token::RParen) {
                        args.push(self.parse_expr(0)?);
                        if matches!(self.peek(), Token::Comma) { self.advance(); }
                    }
                    self.expect(&Token::RParen, "Expected ')'")?;
                    Ok(Spanned { value: Expr::Call(name, args), span })
                } else {
                    Ok(Spanned { value: Expr::Ident(name), span })
                }
            }
            Token::V => {
                self.advance();
                Ok(Spanned { value: Expr::Ident("v".to_string()), span })
            }
            Token::LBracket => {
                self.advance();
                let mut items = Vec::new();
                while !matches!(self.peek(), Token::RBracket) {
                    items.push(self.parse_expr(0)?);
                    if matches!(self.peek(), Token::Comma) { self.advance(); }
                }
                self.expect(&Token::RBracket, "Expected ']'")?;
                Ok(Spanned { value: Expr::List(items), span })
            }
            Token::LBrace => {
                self.advance();
                let mut fields = Vec::new();
                while !matches!(self.peek(), Token::RBrace) {
                    if let Token::Str(k) = &self.peek() { let k = k.clone(); self.advance();
                        self.expect(&Token::Colon, "Expected ':'")?;
                        let v = self.parse_expr(0)?;
                        fields.push((k, v));
                        if matches!(self.peek(), Token::Comma) { self.advance(); }
                    } else if let Token::Ident(k) = &self.peek() { let k = k.clone(); self.advance();
                        self.expect(&Token::Colon, "Expected ':'")?;
                        let v = self.parse_expr(0)?;
                        fields.push((k, v));
                        if matches!(self.peek(), Token::Comma) { self.advance(); }
                    } else { break; }
                }
                self.expect(&Token::RBrace, "Expected '}'")?;
                Ok(Spanned { value: Expr::Record(String::new(), fields), span })
            }
            Token::MetaStart => {
                self.advance();
                let _expr = self.parse_expr(0)?;
                Ok(Spanned { value: Expr::MetaString("".into()), span })
            }
            Token::Star => { self.advance(); let expr = self.parse_primary()?;
                Ok(Spanned { value: Expr::Unary(UnaryOp::Neg, Box::new(expr)), span }) }
            _ => Err(ParseError { message: format!("Unexpected token in expression: {:?}", self.peek()), span: Some(span) }),
        }
    }

    fn parse_block(&mut self, ctx: &str) -> Result<Vec<Spanned<Stmt>>, ParseError> {
        let mut stmts = Vec::new();
        self.skip_newlines();
        // In if/else blocks: Return/Render are top-level (stop after one nested statement)
        // In fn/while/foreach/program: only structural tokens are top-level
        let is_if_body = ctx == "if" || ctx == "else";
        let _is_program = ctx == "program";
        let top_level = |t: &Token| {
            if is_if_body {
                matches!(t, Token::End | Token::Fn | Token::T | Token::V | Token::P | Token::Agent | Token::Cap | Token::Contract | Token::Import | Token::Else | Token::Return)
            } else {
                // Fn/While/ForEach body: stop only at structural tokens
                matches!(t, Token::End | Token::Fn | Token::T | Token::V | Token::P | Token::Agent | Token::Cap | Token::Contract | Token::Import | Token::Else)
            }
        };
        // If/else body: first statement is not top-level (it starts with if/else keywords)
        // Always read at least one statement, then check for top-level
        stmts.push(self.parse_stmt()?);
        self.skip_newlines();
        while !top_level(self.peek()) {
            stmts.push(self.parse_stmt()?);
            self.skip_newlines();
        }
        Ok(stmts)
    }

    // Stub implementations for remaining declarations
    fn parse_protocol_decl(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        let name = if let Token::Ident(n) = &self.peek() { let n = n.clone(); self.advance(); n } else { String::new() };
        self.expect(&Token::Colon, "Expected ':'")?;
        Ok(Spanned { value: Stmt::ProtocolDecl(ProtocolDecl { name, msgs: vec![], constraints: vec![] }), span })
    }
    fn parse_agent_decl(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::AgentDecl(AgentDecl { name: String::new(), protocol: String::new(), state: None, handlers: vec![] }), span })
    }
    fn parse_cap_decl(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::CapDecl(CapDecl { name: String::new(), inputs: vec![], outputs: vec![], cost: None, requires: None, safety: vec![] }), span })
    }
    fn parse_contract_decl(&mut self) -> Result<Spanned<Stmt>, ParseError> {
        let span = self.peek_span().clone(); self.advance();
        Ok(Spanned { value: Stmt::ContractDecl(ContractDecl { name: String::new(), params: vec![], pre: vec![], post: vec![], invariant: vec![] }), span })
    }
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Parse error: {}", self.message)
    }
}
