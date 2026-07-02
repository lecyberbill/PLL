use std::collections::HashMap;
use std::sync::Arc;
use crate::opcodes::*;

pub const BUILTIN_EMIT: u8 = 1;
pub const BUILTIN_RENDER: u8 = 2;
pub const BUILTIN_DB_SET: u8 = 3;
pub const BUILTIN_VERIFY: u8 = 4;
pub const BUILTIN_DB_GET: u8 = 5;
pub const BUILTIN_PRINT: u8 = 6;
pub const BUILTIN_STR_CONCAT: u8 = 10;
pub const BUILTIN_STR_LENGTH: u8 = 11;
pub const BUILTIN_STR_SLICE: u8 = 12;
pub const BUILTIN_STR_CHAR_AT: u8 = 13;
pub const BUILTIN_STR_TO_NUM: u8 = 14;
pub const BUILTIN_STR_FROM_NUM: u8 = 15;
pub const BUILTIN_STR_STARTS_WITH: u8 = 16;
pub const BUILTIN_STR_TO_UPPER: u8 = 18;
pub const BUILTIN_LIST_LENGTH: u8 = 20;
pub const BUILTIN_LIST_GET: u8 = 21;
pub const BUILTIN_LIST_PUSH: u8 = 22;
pub const BUILTIN_NOT: u8 = 28;
pub const BUILTIN_LIST_IN: u8 = 30;
pub const BUILTIN_SEMANTIC_INVERT: u8 = 31;
pub const BUILTIN_ARGS: u8 = 40;
pub const BUILTIN_READ_FILE: u8 = 41;
pub const BUILTIN_WRITE_FILE: u8 = 42;

fn decode_str<'a>(code: &'a [u8], ip: &mut usize) -> &'a str {
    let len = code[*ip] as usize; *ip += 1;
    let s = std::str::from_utf8(&code[*ip..*ip + len]).unwrap_or("");
    *ip += len;
    s
}

fn decode_i16(code: &[u8], ip: &mut usize) -> i16 {
    let val = i16::from_le_bytes([code[*ip], code[*ip + 1]]);
    *ip += 2;
    val
}

#[derive(Debug, Clone)]
pub enum BcValue {
    Num(f64), Str(String), Bool(bool),
    List(Arc<Vec<BcValue>>),
    Record(Arc<HashMap<String, BcValue>>),
    Nil,
}

impl BcValue {
    pub fn type_name(&self) -> &str {
        match self { BcValue::Num(_) => "num", BcValue::Str(_) => "String", BcValue::Bool(_) => "bool", BcValue::List(_) => "list", BcValue::Record(_) => "record", BcValue::Nil => "nil" }
    }
    pub fn as_num(&self) -> Option<f64> { match self { BcValue::Num(n) => Some(*n), _ => None } }
    pub fn as_str(&self) -> Option<&str> { match self { BcValue::Str(s) => Some(s.as_str()), _ => None } }
    fn truthy(&self) -> bool { match self { BcValue::Bool(b) => *b, BcValue::Num(n) => *n != 0.0, BcValue::Str(s) => !s.is_empty(), BcValue::List(v) => !v.is_empty(), BcValue::Record(m) => !m.is_empty(), BcValue::Nil => false } }
    pub fn to_string(&self) -> String { match self { BcValue::Num(n) => n.to_string(), BcValue::Str(s) => s.clone(), BcValue::Bool(b) => b.to_string(), BcValue::List(items) => format!("[{}]", items.iter().map(|v| v.to_string()).collect::<Vec<_>>().join(", ")), BcValue::Record(map) => format!("{{{}}}", map.iter().map(|(k,v)| format!("{}:{}",k,v.to_string())).collect::<Vec<_>>().join(", ")), BcValue::Nil => "nil".to_string(), } }
}

#[derive(Clone)]
pub struct FnInfo {
    pub name: String,
    pub params: Vec<String>,
    pub address: usize,
}

pub struct BcEnv {
    code: Vec<u8>,
    ip: usize,
    stack: Vec<BcValue>,
    pub vars: HashMap<String, BcValue>,
    fns: Vec<FnInfo>,
    call_stack: Vec<(usize, HashMap<String, BcValue>)>,
    running: bool,
}

impl BcEnv {
    pub fn new(code: Vec<u8>) -> Self {
        Self { code, ip: 0, stack: Vec::new(), vars: HashMap::new(), fns: Vec::new(), call_stack: Vec::new(), running: true }
    }

    fn push(&mut self, val: BcValue) { self.stack.push(val); }
    fn pop(&mut self) -> BcValue { self.stack.pop().unwrap_or(BcValue::Nil) }

    pub fn run(&mut self) -> Result<(), String> {
        if self.code[self.ip] == Opcode::FnTable as u8 {
            self.ip += 1;
            let count = self.code[self.ip] as usize;
            self.ip += 1;
            for _ in 0..count {
                let addr = i32::from_le_bytes([self.code[self.ip], self.code[self.ip+1], self.code[self.ip+2], self.code[self.ip+3]]) as usize;
                self.ip += 4;
                self.fns.push(FnInfo { name: String::new(), params: vec![], address: addr });
            }
        }
        while self.running && self.ip < self.code.len() {
            let opcode = self.code[self.ip]; self.ip += 1;
            match Opcode::from_repr(opcode) {
                Some(Opcode::Nop) => {}
                Some(Opcode::PushNum) => {
                    let n = f64::from_le_bytes([self.code[self.ip], self.code[self.ip+1], self.code[self.ip+2], self.code[self.ip+3], self.code[self.ip+4], self.code[self.ip+5], self.code[self.ip+6], self.code[self.ip+7]]);
                    self.ip += 8; self.push(BcValue::Num(n));
                }
                Some(Opcode::PushStr) => { let s = decode_str(&self.code, &mut self.ip).to_string(); self.push(BcValue::Str(s)); }
                Some(Opcode::PushBool) => { self.push(BcValue::Bool(self.code[self.ip] != 0)); self.ip += 1; }
                Some(Opcode::PushNil) => { self.push(BcValue::Nil); }
                Some(Opcode::Pop) => { self.pop(); }
                Some(Opcode::Add) => { let b = self.pop().as_num().unwrap_or(0.0); let a = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Num(a + b)); }
                Some(Opcode::Sub) => { let b = self.pop().as_num().unwrap_or(0.0); let a = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Num(a - b)); }
                Some(Opcode::Mul) => { let b = self.pop().as_num().unwrap_or(0.0); let a = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Num(a * b)); }
                Some(Opcode::Div) => { let b = self.pop().as_num().unwrap_or(0.0); let a = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Num(a / b)); }
                Some(Opcode::Eq) => { let b = self.pop(); let a = self.pop(); self.push(BcValue::Bool(a.to_string() == b.to_string())); }
                Some(Opcode::Neq) => { let b = self.pop(); let a = self.pop(); self.push(BcValue::Bool(a.to_string() != b.to_string())); }
                Some(Opcode::Gt) => { let b = self.pop().as_num().unwrap_or(0.0); let a = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Bool(a > b)); }
                Some(Opcode::Lt) => { let b = self.pop().as_num().unwrap_or(0.0); let a = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Bool(a < b)); }
                Some(Opcode::Gte) => { let b = self.pop().as_num().unwrap_or(0.0); let a = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Bool(a >= b)); }
                Some(Opcode::Lte) => { let b = self.pop().as_num().unwrap_or(0.0); let a = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Bool(a <= b)); }
                Some(Opcode::And) => { let b = self.pop().truthy(); let a = self.pop().truthy(); self.push(BcValue::Bool(a && b)); }
                Some(Opcode::Or) => { let b = self.pop().truthy(); let a = self.pop().truthy(); self.push(BcValue::Bool(a || b)); }
                Some(Opcode::Not) => { let v = self.pop().truthy(); self.push(BcValue::Bool(!v)); }
                Some(Opcode::LoadVar) => { let name = decode_str(&self.code, &mut self.ip).to_string(); self.push(self.vars.get(&name).cloned().unwrap_or(BcValue::Nil)); }
                Some(Opcode::StoreVar) => { let name = decode_str(&self.code, &mut self.ip).to_string(); let val = self.pop(); self.vars.insert(name, val); }
                Some(Opcode::Jmp) => { let offset = decode_i16(&self.code, &mut self.ip); self.ip = ((self.ip as i64) + (offset as i64)) as usize; }
                Some(Opcode::Jif) => { let offset = decode_i16(&self.code, &mut self.ip); if !self.pop().truthy() { self.ip = ((self.ip as i64) + (offset as i64)) as usize; } }
                Some(Opcode::Call) => {
                    let argc = self.code[self.ip] as usize; self.ip += 1;
                    let fn_idx = self.code[self.ip] as usize; self.ip += 1;
                    if fn_idx >= self.fns.len() { for _ in 0..argc { self.pop(); } self.push(BcValue::Nil); }
                    else {
                        let ip_now = self.ip;
                        let fn_info = self.fns[fn_idx].clone();
                        let saved = self.vars.clone();
                        let mut call_args = Vec::new();
                        for _ in 0..argc { call_args.push(self.pop()); }
                        call_args.reverse();
                        self.call_stack.push((ip_now, saved));
                        for (i, param) in fn_info.params.iter().enumerate() { if i < call_args.len() { self.vars.insert(param.clone(), call_args[i].clone()); } }
                        self.ip = fn_info.address;
                    }
                }
                Some(Opcode::Ret) => {
                    let ret_val = self.pop();
                    if let Some((ip, saved)) = self.call_stack.pop() { self.vars = saved; self.ip = ip; self.push(ret_val); }
                    else { self.push(ret_val); self.running = false; }
                }
                Some(Opcode::Builtin) => { let id = self.code[self.ip]; self.ip += 1; self.exec_builtin(id)?; }
                Some(Opcode::ListNew) => { self.push(BcValue::List(Arc::new(Vec::new()))); }
                Some(Opcode::ListPush) => { let item = self.pop(); let mut items = if let BcValue::List(list) = self.pop() { (*list).clone() } else { vec![] }; items.push(item); self.push(BcValue::List(Arc::new(items))); }
                Some(Opcode::ListGet) => { let idx = self.pop().as_num().unwrap_or(0.0) as usize; if let BcValue::List(items) = self.pop() { self.push(items.get(idx).cloned().unwrap_or(BcValue::Nil)); } else { self.push(BcValue::Nil); } }
                Some(Opcode::ListLen) => { let len = if let BcValue::List(items) = self.pop() { items.len() as f64 } else { 0.0 }; self.push(BcValue::Num(len)); }
                Some(Opcode::RecordNew) => { self.push(BcValue::Record(Arc::new(HashMap::new()))); }
                Some(Opcode::RecordSet) => { let val = self.pop(); let key = self.pop().to_string(); if let BcValue::Record(ref mut map) = self.stack.last_mut().unwrap() { Arc::make_mut(map).insert(key, val); } }
                Some(Opcode::Field) => { let field = self.pop().to_string(); if let BcValue::Record(map) = self.pop() { self.push(map.get(&field).cloned().unwrap_or(BcValue::Nil)); } else { self.push(BcValue::Nil); } }
                Some(Opcode::FnTable) => {}
                Some(Opcode::Halt) => { self.running = false; }
                None => return Err(format!("Unknown opcode {}", opcode)),
            }
        }
        Ok(())
    }

    fn exec_builtin(&mut self, id: u8) -> Result<(), String> {
        match id {
            BUILTIN_EMIT => { let v = self.pop().to_string(); pll_runtime::pll_emit(&v); }
            BUILTIN_RENDER => { let v = self.pop().to_string(); pll_runtime::pll_render(&v); }
            BUILTIN_DB_SET => { let v = self.pop().to_string(); let k = self.pop().to_string(); pll_runtime::pll_db_set(k, v); }
            BUILTIN_DB_GET => { let k = self.pop().to_string(); self.push(BcValue::Str(pll_runtime::pll_db_get(&k).unwrap_or_default())); }
            BUILTIN_PRINT => { let v = self.pop().to_string(); pll_runtime::pll_print(&v); }
            BUILTIN_STR_CONCAT => { let b = self.pop().to_string(); let a = self.pop().to_string(); self.push(BcValue::Str(format!("{}{}", a, b))); }
            BUILTIN_STR_LENGTH => { let s = self.pop().to_string(); self.push(BcValue::Num(s.chars().count() as f64)); }
            BUILTIN_STR_SLICE => { let end = self.pop().as_num().unwrap_or(0.0); let start = self.pop().as_num().unwrap_or(0.0); let s = self.pop().to_string(); self.push(BcValue::Str(pll_runtime::str_slice(&s, start, end))); }
            BUILTIN_STR_CHAR_AT => { let i = self.pop().as_num().unwrap_or(0.0); let s = self.pop().to_string(); let c = s.chars().nth(i as usize).map(|c| c.to_string()).unwrap_or_default(); self.push(BcValue::Str(c)); }
            BUILTIN_STR_TO_NUM => { let s = self.pop().to_string(); self.push(BcValue::Num(pll_runtime::str_to_num(&s))); }
            BUILTIN_STR_FROM_NUM => { let n = self.pop().as_num().unwrap_or(0.0); self.push(BcValue::Str(pll_runtime::str_from_num(n))); }
            BUILTIN_STR_STARTS_WITH => { let p = self.pop().to_string(); let s = self.pop().to_string(); self.push(BcValue::Bool(pll_runtime::str_starts_with(&s, &p))); }
            BUILTIN_STR_TO_UPPER => { let s = self.pop().to_string(); self.push(BcValue::Str(s.to_uppercase())); }
            BUILTIN_LIST_LENGTH => { let len = if let BcValue::List(list) = self.pop() { list.len() as f64 } else { 0.0 }; self.push(BcValue::Num(len)); }
            BUILTIN_LIST_GET => { let idx = self.pop().as_num().unwrap_or(0.0) as usize; if let BcValue::List(items) = self.pop() { self.push(items.get(idx).cloned().unwrap_or(BcValue::Nil)); } else { return Err("list_get requires list".to_string()); } }
            BUILTIN_LIST_PUSH => { let item = self.pop(); let mut items = if let BcValue::List(list) = self.pop() { (*list).clone() } else { vec![] }; items.push(item); self.push(BcValue::List(Arc::new(items))); }
            BUILTIN_ARGS => { let args: Vec<BcValue> = pll_runtime::pll_args().into_iter().map(BcValue::Str).collect(); self.push(BcValue::List(Arc::new(args))); }
            BUILTIN_READ_FILE => { let path = self.pop().to_string(); let content = pll_runtime::pll_read_file(&path).unwrap_or_default(); self.push(BcValue::Str(content)); }
            BUILTIN_WRITE_FILE => { let content = self.pop().to_string(); let path = self.pop().to_string(); let _ = pll_runtime::pll_write_file(&path, &content); self.push(BcValue::Nil); }
            _ => return Err(format!("Unknown builtin {}", id)),
        }
        Ok(())
    }
}

impl Opcode {
    fn from_repr(id: u8) -> Option<Self> {
        match id {
            0 => Some(Opcode::Nop), 1 => Some(Opcode::PushNum), 2 => Some(Opcode::PushStr),
            3 => Some(Opcode::PushBool), 4 => Some(Opcode::PushNil), 5 => Some(Opcode::Pop),
            10 => Some(Opcode::Add), 11 => Some(Opcode::Sub), 12 => Some(Opcode::Mul), 13 => Some(Opcode::Div),
            20 => Some(Opcode::Eq), 21 => Some(Opcode::Neq), 22 => Some(Opcode::Gt), 23 => Some(Opcode::Lt),
            24 => Some(Opcode::Gte), 25 => Some(Opcode::Lte), 26 => Some(Opcode::And), 27 => Some(Opcode::Or), 28 => Some(Opcode::Not),
            30 => Some(Opcode::LoadVar), 31 => Some(Opcode::StoreVar),
            40 => Some(Opcode::Jmp), 41 => Some(Opcode::Jif),
            50 => Some(Opcode::Call), 51 => Some(Opcode::Ret),
            60 => Some(Opcode::Builtin),
            70 => Some(Opcode::ListNew), 71 => Some(Opcode::ListPush), 72 => Some(Opcode::ListGet), 73 => Some(Opcode::ListLen),
            74 => Some(Opcode::RecordNew), 75 => Some(Opcode::RecordSet), 76 => Some(Opcode::Field),
            80 => Some(Opcode::FnTable), 255 => Some(Opcode::Halt),
            _ => None,
        }
    }
}
