use crate::opcodes::*;
use pll_core::*;

pub struct Compiler {
    bytecode: Vec<u8>,
    fns: Vec<FnInfo>,
    vars: std::collections::HashMap<String, u16>,
}

#[derive(Clone)]
pub struct FnInfo {
    pub name: String,
    pub params: Vec<String>,
    pub address: usize,
}

impl Compiler {
    pub fn new() -> Self {
        Self { bytecode: Vec::new(), fns: Vec::new(), vars: std::collections::HashMap::new() }
    }

    pub fn compile_program(&mut self, program: &Program) {
        // First pass: collect function declarations
        let mut fn_decls = Vec::new();
        for stmt in &program.statements {
            if let Stmt::FnDecl(f) = &stmt.value {
                fn_decls.push(f.clone());
            }
        }
        // Reserve function table space
        self.bytecode.push(Opcode::FnTable as u8);
        self.bytecode.push(fn_decls.len() as u8);
        let fn_table_pos = self.bytecode.len();
        // Placeholder addresses
        for _ in &fn_decls {
            self.bytecode.extend_from_slice(&[0; 4]);
        }
        // Compile function bodies
        let mut fn_addrs = Vec::new();
        for f in &fn_decls {
            let addr = self.bytecode.len();
            fn_addrs.push(addr);
            self.vars.clear();
            for p in &f.params {
                let var_idx = self.vars.len() as u16;
                self.vars.insert(p.name.clone(), var_idx);
            }
            for s in &f.body {
                self.compile_stmt(s);
            }
            self.bytecode.push(Opcode::Ret as u8);
        }
        // Patch function addresses
        for (i, addr) in fn_addrs.iter().enumerate() {
            let pos = fn_table_pos + i * 4;
            let bytes = (*addr as i32).to_le_bytes();
            self.bytecode[pos..pos + 4].copy_from_slice(&bytes);
        }
        // Compile main body
        for stmt in &program.statements {
            match &stmt.value {
                Stmt::FnDecl(_) => {}
                _ => self.compile_stmt(stmt),
            }
        }
        self.bytecode.push(Opcode::Halt as u8);
    }

    fn compile_stmt(&mut self, stmt: &Spanned<Stmt>) {
        match &stmt.value {
            Stmt::VarDecl(v) => {
                if let Some(init) = &v.init {
                    self.compile_expr(init);
                } else {
                    self.bytecode.push(Opcode::PushNil as u8);
                }
                let idx = self.vars.len() as u16;
                self.vars.insert(v.name.clone(), idx);
                self.emit_store_var(&v.name);
            }
            Stmt::Assign { name, value } => {
                self.compile_expr(value);
                self.emit_store_var(name);
            }
            Stmt::Render(e) => { self.compile_expr(e); self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, 2]); }
            Stmt::Print(e) => { self.compile_expr(e); self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, 6]); }
            Stmt::Emit(e) => { self.compile_expr(e); self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, 1]); }
            Stmt::Return(e) => { self.compile_expr(e); self.bytecode.push(Opcode::Ret as u8); }
            Stmt::Expr(e) => { self.compile_expr(e); self.bytecode.push(Opcode::Pop as u8); }
            Stmt::If(i) => {
                self.compile_expr(&i.condition);
                let jif_pos = self.bytecode.len();
                self.bytecode.push(Opcode::Jif as u8);
                self.bytecode.extend_from_slice(&[0; 2]);
                for s in &i.then_body { self.compile_stmt(s); }
                if i.else_body.is_some() {
                    let jmp_pos = self.bytecode.len();
                    self.bytecode.push(Opcode::Jmp as u8);
                    self.bytecode.extend_from_slice(&[0; 2]);
                    let else_start = self.bytecode.len();
                    if let Some(el) = &i.else_body { for s in el { self.compile_stmt(s); } }
                    let else_end = self.bytecode.len();
                    let jif_offset = (else_start as i16 - jif_pos as i16 - 3) as i16;
                    self.bytecode[jif_pos + 1..jif_pos + 3].copy_from_slice(&jif_offset.to_le_bytes());
                    let jmp_offset = (else_end as i16 - jmp_pos as i16 - 3) as i16;
                    self.bytecode[jmp_pos + 1..jmp_pos + 3].copy_from_slice(&jmp_offset.to_le_bytes());
                } else {
                    let after = self.bytecode.len();
                    let jif_offset = (after as i16 - jif_pos as i16 - 3) as i16;
                    self.bytecode[jif_pos + 1..jif_pos + 3].copy_from_slice(&jif_offset.to_le_bytes());
                }
            }
            Stmt::While(w) => {
                let loop_start = self.bytecode.len();
                self.compile_expr(&w.condition);
                let jif_pos = self.bytecode.len();
                self.bytecode.push(Opcode::Jif as u8);
                self.bytecode.extend_from_slice(&[0; 2]);
                for s in &w.body { self.compile_stmt(s); }
                let jmp_offset = (loop_start as i16 - self.bytecode.len() as i16 - 3) as i16;
                self.bytecode.push(Opcode::Jmp as u8);
                self.bytecode.extend_from_slice(&jmp_offset.to_le_bytes());
                let after = self.bytecode.len();
                let jif_offset = (after as i16 - jif_pos as i16 - 3) as i16;
                self.bytecode[jif_pos + 1..jif_pos + 3].copy_from_slice(&jif_offset.to_le_bytes());
            }
            _ => {}
        }
    }

    fn compile_expr(&mut self, expr: &Spanned<Expr>) {
        match &expr.value {
            Expr::Literal(lit) => match lit {
                Literal::Num(n) => { self.bytecode.push(Opcode::PushNum as u8); self.bytecode.extend_from_slice(&n.to_le_bytes()); }
                Literal::Str(s) => { self.emit_push_str(s); }
                Literal::Bool(b) => { self.bytecode.push(Opcode::PushBool as u8); self.bytecode.push(if *b { 1 } else { 0 }); }
                Literal::Nil => { self.bytecode.push(Opcode::PushNil as u8); }
            },
            Expr::Ident(name) => { self.emit_load_var(name); }
            Expr::Binary(op, left, right) => {
                self.compile_expr(left);
                self.compile_expr(right);
                let opcode = match op {
                    BinaryOp::Add => Opcode::Add, BinaryOp::Sub => Opcode::Sub,
                    BinaryOp::Mul => Opcode::Mul, BinaryOp::Div => Opcode::Div,
                    BinaryOp::Eq => Opcode::Eq, BinaryOp::Neq => Opcode::Neq,
                    BinaryOp::Gt => Opcode::Gt, BinaryOp::Lt => Opcode::Lt,
                    BinaryOp::Gte => Opcode::Gte, BinaryOp::Lte => Opcode::Lte,
                    BinaryOp::And => Opcode::And, BinaryOp::Or => Opcode::Or,
                    _ => Opcode::Add,
                };
                self.bytecode.push(opcode as u8);
            }
            Expr::Call(name, args) => {
                for a in args.iter().rev() { self.compile_expr(a); }
                self.bytecode.push(Opcode::Call as u8);
                self.bytecode.push(args.len() as u8);
                let fn_idx = self.fns.iter().position(|f| f.name == *name).unwrap_or(0) as u8;
                self.bytecode.push(fn_idx);
            }
            Expr::List(items) => {
                self.bytecode.push(Opcode::ListNew as u8);
                for i in items { self.compile_expr(i); self.bytecode.push(Opcode::ListPush as u8); }
            }
            _ => { self.bytecode.push(Opcode::PushNil as u8); }
        }
    }

    fn emit_push_str(&mut self, s: &str) {
        self.bytecode.push(Opcode::PushStr as u8);
        let bytes = s.as_bytes();
        self.bytecode.push(bytes.len() as u8);
        self.bytecode.extend_from_slice(bytes);
    }

    fn emit_load_var(&mut self, name: &str) {
        self.bytecode.push(Opcode::LoadVar as u8);
        let bytes = name.as_bytes();
        self.bytecode.push(bytes.len() as u8);
        self.bytecode.extend_from_slice(bytes);
    }

    fn emit_store_var(&mut self, name: &str) {
        self.bytecode.push(Opcode::StoreVar as u8);
        let bytes = name.as_bytes();
        self.bytecode.push(bytes.len() as u8);
        self.bytecode.extend_from_slice(bytes);
    }

    pub fn into_bytecode(self) -> Vec<u8> { self.bytecode }
    pub fn fns(&self) -> &[FnInfo] { &self.fns }
}
