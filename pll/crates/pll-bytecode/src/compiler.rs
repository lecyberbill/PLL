use crate::opcodes::*;
use crate::vm::{BUILTIN_RENDER, BUILTIN_PRINT, BUILTIN_EMIT, BUILTIN_STR_CONCAT, BUILTIN_STR_LENGTH, BUILTIN_STR_SLICE, BUILTIN_STR_CHAR_AT, BUILTIN_STR_TO_NUM, BUILTIN_STR_FROM_NUM, BUILTIN_STR_STARTS_WITH, BUILTIN_STR_TO_UPPER, BUILTIN_LIST_LENGTH, BUILTIN_LIST_GET, BUILTIN_LIST_PUSH, BUILTIN_READ_FILE, BUILTIN_WRITE_FILE, BUILTIN_DB_SET, BUILTIN_DB_GET};
use pll_core::*;

pub struct Compiler {
    bytecode: Vec<u8>,
    fns: Vec<FnInfo>,
    vars: std::collections::HashMap<String, u16>,
    globals: std::collections::HashMap<String, u16>,
    is_compiling_fn: bool,
}

#[derive(Clone)]
pub struct FnInfo {
    pub name: String,
    pub params: Vec<String>,
    pub address: usize,
}

impl Compiler {
    pub fn new() -> Self {
        Self {
            bytecode: Vec::new(),
            fns: Vec::new(),
            vars: std::collections::HashMap::new(),
            globals: std::collections::HashMap::new(),
            is_compiling_fn: false,
        }
    }

    pub fn compile_program(&mut self, program: &Program) {
        let mut fn_decls = Vec::new();
        for stmt in &program.statements {
            if let Stmt::FnDecl(f) = &stmt.value { fn_decls.push(f.clone()); }
        }
        for f in &fn_decls {
            self.fns.push(FnInfo {
                name: f.name.clone(),
                params: f.params.iter().map(|p| p.name.clone()).collect(),
                address: 0,
            });
        }
        self.bytecode.extend_from_slice(&[0; 4]);
        self.is_compiling_fn = false;
        for stmt in &program.statements {
            match &stmt.value { Stmt::FnDecl(_) => {} _ => self.compile_stmt(stmt), }
        }
        self.bytecode.push(Opcode::Halt as u8);
        let fn_table_start = self.bytecode.len();
        self.bytecode.push(Opcode::FnTable as u8);
        self.bytecode.push(fn_decls.len() as u8);
        let mut fn_addr_positions = Vec::new();
        for f in &fn_decls {
            fn_addr_positions.push(self.bytecode.len());
            self.bytecode.extend_from_slice(&[0; 4]);
            let name_bytes = f.name.as_bytes();
            self.bytecode.push(name_bytes.len() as u8);
            self.bytecode.extend_from_slice(name_bytes);
        }
        self.is_compiling_fn = true;
        let mut fn_addrs = Vec::new();
        for (i, f) in fn_decls.iter().enumerate() {
            let addr = self.bytecode.len();
            fn_addrs.push(addr);
            self.fns[i].address = addr;
            self.vars.clear();
            for p in &f.params {
                let idx = self.vars.len() as u16;
                self.vars.insert(p.name.clone(), idx);
                self.emit_store_var(&p.name);
            }
            for s in &f.body { self.compile_stmt(s); }
            self.bytecode.push(Opcode::Ret as u8);
        }
        for (i, addr) in fn_addrs.iter().enumerate() {
            let pos = fn_addr_positions[i];
            self.bytecode[pos..pos + 4].copy_from_slice(&(*addr as i32).to_le_bytes());
        }
        let offset = (fn_table_start as i32 - 0) as i32;
        self.bytecode[0..4].copy_from_slice(&offset.to_le_bytes());
    }

    fn compile_stmt(&mut self, stmt: &Spanned<Stmt>) {
        match &stmt.value {
            Stmt::VarDecl(v) => {
                if let Some(init) = &v.init { self.compile_expr(init); } else { self.bytecode.push(Opcode::PushNil as u8); }
                if self.is_compiling_fn {
                    let idx = self.vars.len() as u16;
                    self.vars.insert(v.name.clone(), idx);
                } else {
                    let idx = self.globals.len() as u16;
                    self.globals.insert(v.name.clone(), idx);
                }
                self.emit_store_var(&v.name);
            }
            Stmt::Assign { name, value } => { self.compile_expr(value); self.emit_store_var(name); }
            Stmt::Render(e) => { self.compile_expr(e); self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, BUILTIN_RENDER]); }
            Stmt::Print(e) => { self.compile_expr(e); self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, BUILTIN_PRINT]); }
            Stmt::Emit(e) => { self.compile_expr(e); self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, BUILTIN_EMIT]); }
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
                    let after = self.bytecode.len();
                    let jif_offset = (else_start as i16 - jif_pos as i16 - 3) as i16;
                    self.bytecode[jif_pos + 1..jif_pos + 3].copy_from_slice(&jif_offset.to_le_bytes());
                    let jmp_off = (after as i16 - jmp_pos as i16 - 3) as i16;
                    self.bytecode[jmp_pos + 1..jmp_pos + 3].copy_from_slice(&jmp_off.to_le_bytes());
                } else {
                    let after = self.bytecode.len();
                    let jif_off = (after as i16 - jif_pos as i16 - 3) as i16;
                    self.bytecode[jif_pos + 1..jif_pos + 3].copy_from_slice(&jif_off.to_le_bytes());
                }
            }
            Stmt::While(w) => {
                let loop_start = self.bytecode.len();
                self.compile_expr(&w.condition);
                let jif_pos = self.bytecode.len();
                self.bytecode.push(Opcode::Jif as u8);
                self.bytecode.extend_from_slice(&[0; 2]);
                for s in &w.body { self.compile_stmt(s); }
                let jmp_off = (loop_start as i16 - self.bytecode.len() as i16 - 3) as i16;
                self.bytecode.push(Opcode::Jmp as u8);
                self.bytecode.extend_from_slice(&jmp_off.to_le_bytes());
                let after = self.bytecode.len();
                let jif_off = (after as i16 - jif_pos as i16 - 3) as i16;
                self.bytecode[jif_pos + 1..jif_pos + 3].copy_from_slice(&jif_off.to_le_bytes());
            }
            Stmt::ForEach(fe) => {
                let list_var = "__fe_list";
                let idx_var = "__fe_idx";
                self.compile_expr(&fe.iter);
                self.emit_store_var(list_var);
                self.vars.insert(list_var.to_string(), 0);
                self.bytecode.extend_from_slice(&[Opcode::PushNum as u8]);
                self.bytecode.extend_from_slice(&0.0f64.to_le_bytes());
                self.emit_store_var(idx_var);
                self.vars.insert(idx_var.to_string(), 0);
                let loop_start = self.bytecode.len();
                self.emit_load_var(idx_var);
                self.emit_load_var(list_var);
                self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, BUILTIN_LIST_LENGTH]);
                self.bytecode.push(Opcode::Lt as u8);
                let jif_pos = self.bytecode.len();
                self.bytecode.push(Opcode::Jif as u8);
                self.bytecode.extend_from_slice(&[0; 2]);
                self.emit_load_var(list_var);
                self.emit_load_var(idx_var);
                self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, BUILTIN_LIST_GET]);
                self.emit_store_var(&fe.var);
                self.vars.insert(fe.var.clone(), 0);
                for s in &fe.body { self.compile_stmt(s); }
                self.emit_load_var(idx_var);
                self.bytecode.extend_from_slice(&[Opcode::PushNum as u8]);
                self.bytecode.extend_from_slice(&1.0f64.to_le_bytes());
                self.bytecode.push(Opcode::Add as u8);
                self.emit_store_var(idx_var);
                let jmp_off = (loop_start as i16 - self.bytecode.len() as i16 - 3) as i16;
                self.bytecode.push(Opcode::Jmp as u8);
                self.bytecode.extend_from_slice(&jmp_off.to_le_bytes());
                let after = self.bytecode.len();
                let jif_off = (after as i16 - jif_pos as i16 - 3) as i16;
                self.bytecode[jif_pos + 1..jif_pos + 3].copy_from_slice(&jif_off.to_le_bytes());
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
                self.compile_expr(left); self.compile_expr(right);
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
                let builtin_id = match name.as_str() {
                    "render" => Some(BUILTIN_RENDER),
                    "print" => Some(BUILTIN_PRINT),
                    "str_concat" => Some(BUILTIN_STR_CONCAT),
                    "str_length" => Some(BUILTIN_STR_LENGTH),
                    "str_slice" => Some(BUILTIN_STR_SLICE),
                    "str_char_at" => Some(BUILTIN_STR_CHAR_AT),
                    "str_to_num" => Some(BUILTIN_STR_TO_NUM),
                    "str_from_num" => Some(BUILTIN_STR_FROM_NUM),
                    "str_starts_with" => Some(BUILTIN_STR_STARTS_WITH),
                    "str_to_upper" => Some(BUILTIN_STR_TO_UPPER),
                    "list_length" => Some(BUILTIN_LIST_LENGTH),
                    "list_get" => Some(BUILTIN_LIST_GET),
                    "list_push" => Some(BUILTIN_LIST_PUSH),
                    "read_file" => Some(BUILTIN_READ_FILE),
                    "write_file" => Some(BUILTIN_WRITE_FILE),
                    "db_set" => Some(BUILTIN_DB_SET),
                    "db_read" => Some(BUILTIN_DB_GET),
                    _ => None,
                };
                if let Some(id) = builtin_id {
                    for a in args.iter() { self.compile_expr(a); }
                    self.bytecode.push(Opcode::Builtin as u8);
                    self.bytecode.push(id);
                } else {
                    for a in args.iter() { self.compile_expr(a); }
                    self.bytecode.push(Opcode::Call as u8);
                    self.bytecode.push(args.len() as u8);
                    let fn_idx = self.fns.iter().position(|f| f.name == *name).unwrap_or(0) as u8;
                    self.bytecode.push(fn_idx);
                }
            }
            Expr::List(items) => {
                self.bytecode.push(Opcode::ListNew as u8);
                for i in items { self.compile_expr(i); self.bytecode.push(Opcode::ListPush as u8); }
            }
            Expr::Record(_, fields) => {
                self.bytecode.push(Opcode::RecordNew as u8);
                for (k, v) in fields { self.compile_expr(v); self.emit_push_str(k); self.bytecode.push(Opcode::RecordSet as u8); }
            }
            Expr::Index(obj, idx) => { self.compile_expr(obj); self.compile_expr(idx); self.bytecode.extend_from_slice(&[Opcode::Builtin as u8, BUILTIN_LIST_GET]); }
            Expr::Member(obj, field) => { self.compile_expr(obj); self.emit_push_str(field); self.bytecode.push(Opcode::Field as u8); }
            Expr::Unary(op, expr) => {
                self.compile_expr(expr);
                match op { UnaryOp::Not => self.bytecode.push(Opcode::Not as u8), UnaryOp::Neg => { self.bytecode.push(Opcode::PushNum as u8); self.bytecode.extend_from_slice(&(-1.0f64).to_le_bytes()); self.bytecode.push(Opcode::Mul as u8); } }
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
        if self.is_compiling_fn {
            if let Some(&idx) = self.vars.get(name) {
                self.bytecode.push(Opcode::LoadVarSlot as u8);
                self.bytecode.extend_from_slice(&idx.to_le_bytes());
                return;
            }
        }
        if let Some(&idx) = self.globals.get(name) {
            self.bytecode.push(Opcode::LoadGlobalSlot as u8);
            self.bytecode.extend_from_slice(&idx.to_le_bytes());
            return;
        }
        if self.is_compiling_fn {
            let idx = self.vars.len() as u16;
            self.vars.insert(name.to_string(), idx);
            self.bytecode.push(Opcode::LoadVarSlot as u8);
            self.bytecode.extend_from_slice(&idx.to_le_bytes());
        } else {
            let idx = self.globals.len() as u16;
            self.globals.insert(name.to_string(), idx);
            self.bytecode.push(Opcode::LoadGlobalSlot as u8);
            self.bytecode.extend_from_slice(&idx.to_le_bytes());
        }
    }

    fn emit_store_var(&mut self, name: &str) {
        if self.is_compiling_fn {
            if let Some(&idx) = self.vars.get(name) {
                self.bytecode.push(Opcode::StoreVarSlot as u8);
                self.bytecode.extend_from_slice(&idx.to_le_bytes());
                return;
            }
        }
        if let Some(&idx) = self.globals.get(name) {
            self.bytecode.push(Opcode::StoreGlobalSlot as u8);
            self.bytecode.extend_from_slice(&idx.to_le_bytes());
            return;
        }
        if self.is_compiling_fn {
            let idx = self.vars.len() as u16;
            self.vars.insert(name.to_string(), idx);
            self.bytecode.push(Opcode::StoreVarSlot as u8);
            self.bytecode.extend_from_slice(&idx.to_le_bytes());
        } else {
            let idx = self.globals.len() as u16;
            self.globals.insert(name.to_string(), idx);
            self.bytecode.push(Opcode::StoreGlobalSlot as u8);
            self.bytecode.extend_from_slice(&idx.to_le_bytes());
        }
    }

    pub fn into_bytecode(self) -> Vec<u8> { self.bytecode }
    pub fn fns(&self) -> &[FnInfo] { &self.fns }
}
