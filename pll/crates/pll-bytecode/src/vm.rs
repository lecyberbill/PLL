use std::collections::HashMap;
use std::sync::Arc;
use crate::opcodes::*;

fn decode_str<'a>(code: &'a [u8], ip: &mut usize) -> &'a str {
    let len = code[*ip] as usize;
    *ip += 1;
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
        match self {
            BcValue::Num(_) => "num", BcValue::Str(_) => "String",
            BcValue::Bool(_) => "bool", BcValue::List(_) => "list",
            BcValue::Record(_) => "record", BcValue::Nil => "nil",
        }
    }
    pub fn as_num(&self) -> Option<f64> {
        match self { BcValue::Num(n) => Some(*n), _ => None }
    }
    pub fn as_str(&self) -> Option<&str> {
        match self { BcValue::Str(s) => Some(s.as_str()), _ => None }
    }
    fn truthy(&self) -> bool {
        match self {
            BcValue::Bool(b) => *b, BcValue::Num(n) => *n != 0.0,
            BcValue::Str(s) => !s.is_empty(),
            BcValue::List(v) => !v.is_empty(),
            BcValue::Record(m) => !m.is_empty(),
            BcValue::Nil => false,
        }
    }
    pub fn to_string(&self) -> String {
        match self {
            BcValue::Num(n) => n.to_string(),
            BcValue::Str(s) => s.clone(),
            BcValue::Bool(b) => b.to_string(),
            BcValue::List(items) => {
                let parts: Vec<String> = items.iter().map(|v| v.to_string()).collect();
                format!("[{}]", parts.join(", "))
            }
            BcValue::Record(map) => {
                let parts: Vec<String> = map.iter().map(|(k, v)| format!("{}: {}", k, v.to_string())).collect();
                format!("{{{}}}", parts.join(", "))
            }
            BcValue::Nil => "nil".to_string(),
        }
    }
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
        // Parse function table
        if self.code[self.ip] == Opcode::FnTable as u8 {
            self.ip += 1;
            let count = self.code[self.ip] as usize;
            self.ip += 1;
            for _ in 0..count {
                let addr_bytes: [u8; 4] = [self.code[self.ip], self.code[self.ip + 1], self.code[self.ip + 2], self.code[self.ip + 3]];
                let _addr = i32::from_le_bytes(addr_bytes) as usize;
                self.ip += 4;
                self.fns.push(FnInfo { name: String::new(), params: vec![], address: _addr });
            }
        }

        while self.running && self.ip < self.code.len() {
            let opcode = self.code[self.ip];
            self.ip += 1;
            match Opcode::from_repr(opcode) {
                Some(Opcode::Nop) => {}
                Some(Opcode::PushNum) => {
                    let bytes: [u8; 8] = [self.code[self.ip], self.code[self.ip + 1], self.code[self.ip + 2], self.code[self.ip + 3],
                                           self.code[self.ip + 4], self.code[self.ip + 5], self.code[self.ip + 6], self.code[self.ip + 7]];
                    self.ip += 8;
                    self.push(BcValue::Num(f64::from_le_bytes(bytes)));
                }
                Some(Opcode::PushStr) => {
                    let len = self.code[self.ip] as usize; self.ip += 1;
                    let s = std::str::from_utf8(&self.code[self.ip..self.ip + len]).unwrap_or("").to_string();
                    self.ip += len;
                    self.push(BcValue::Str(s));
                }
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
                Some(Opcode::Not) => { let v = self.pop().truthy(); self.push(BcValue::Bool(!v)); }
                Some(Opcode::And) => { let b = self.pop().truthy(); let a = self.pop().truthy(); self.push(BcValue::Bool(a && b)); }
                Some(Opcode::Or) => { let b = self.pop().truthy(); let a = self.pop().truthy(); self.push(BcValue::Bool(a || b)); }
                Some(Opcode::LoadVar) => {
                    let name = decode_str(&self.code, &mut self.ip).to_string();
                    let val = self.vars.get(&name).cloned().unwrap_or(BcValue::Nil);
                    self.push(val);
                }
                Some(Opcode::StoreVar) => {
                    let name = decode_str(&self.code, &mut self.ip).to_string();
                    let val = self.pop();
                    self.vars.insert(name, val);
                }
                Some(Opcode::Jmp) => { let offset = decode_i16(&self.code, &mut self.ip); self.ip = ((self.ip as i64) + (offset as i64)) as usize; }
                Some(Opcode::Jif) => {
                    let offset = decode_i16(&self.code, &mut self.ip);
                    if !self.pop().truthy() {
                        self.ip = ((self.ip as i64) + (offset as i64)) as usize;
                    }
                }
                Some(Opcode::Call) => {
                    let argc = self.code[self.ip] as usize; self.ip += 1;
                    let fn_idx = self.code[self.ip] as usize; self.ip += 1;
                    if fn_idx >= self.fns.len() {
                        for _ in 0..argc { self.pop(); }
                        self.push(BcValue::Nil);
                    } else {
                        let ip_now = self.ip;
                        let fn_info = self.fns[fn_idx].clone();
                        let saved = self.vars.clone();
                        let mut call_args = Vec::new();
                        for _ in 0..argc { call_args.push(self.pop()); }
                        call_args.reverse();
                        self.call_stack.push((ip_now, saved));
                        for (i, param) in fn_info.params.iter().enumerate() {
                            if i < call_args.len() {
                                self.vars.insert(param.clone(), call_args[i].clone());
                            }
                        }
                        self.ip = fn_info.address;
                    }
                }
                Some(Opcode::Ret) => {
                    let ret_val = self.pop();
                    if let Some((ip, saved_vars)) = self.call_stack.pop() {
                        self.vars = saved_vars;
                        self.ip = ip;
                        self.push(ret_val);
                    } else {
                        self.push(ret_val);
                        self.running = false;
                    }
                }
                Some(Opcode::Builtin) => {
                    let id = self.code[self.ip]; self.ip += 1;
                    self.exec_builtin(id)?;
                }
                Some(Opcode::ListNew) => { self.push(BcValue::List(Arc::new(Vec::new()))); }
                Some(Opcode::ListPush) => {
                    let item = self.pop();
                    let mut items = if let BcValue::List(list) = self.pop() { (*list).clone() } else { vec![] };
                    items.push(item);
                    self.push(BcValue::List(Arc::new(items)));
                }
                Some(Opcode::ListGet) => {
                    let idx = self.pop().as_num().unwrap_or(0.0) as usize;
                    if let BcValue::List(items) = self.pop() {
                        self.push(items.get(idx).cloned().unwrap_or(BcValue::Nil));
                    } else { self.push(BcValue::Nil); }
                }
                Some(Opcode::ListLen) => {
                    let len = if let BcValue::List(items) = self.pop() { items.len() as f64 } else { 0.0 };
                    self.push(BcValue::Num(len));
                }
                Some(Opcode::RecordNew) => {
                    self.push(BcValue::Record(Arc::new(std::collections::HashMap::new())));
                }
                Some(Opcode::RecordSet) => {
                    let val = self.pop();
                    let key = self.pop().to_string();
                    if let BcValue::Record(ref mut map) = self.stack.last_mut().unwrap() {
                        Arc::make_mut(map).insert(key, val);
                    }
                }
                Some(Opcode::Field) => {
                    let field = self.pop().to_string();
                    if let BcValue::Record(map) = self.pop() {
                        self.push(map.get(&field).cloned().unwrap_or(BcValue::Nil));
                    } else { self.push(BcValue::Nil); }
                }
                Some(Opcode::FnTable) => {} // Already parsed at start
                Some(Opcode::Halt) => { self.running = false; }
                None => return Err(format!("Unknown opcode {}", opcode)),
            }
        }
        Ok(())
    }

    fn exec_builtin(&mut self, id: u8) -> Result<(), String> {
        match id {
            1 => { let v = self.pop().to_string(); pll_runtime::pll_emit(&v); }
            2 => { let v = self.pop().to_string(); pll_runtime::pll_render(&v); }
            3 => { let v = self.pop().to_string(); let k = self.pop().to_string(); pll_runtime::pll_db_set(k, v); }
            5 => { let k = self.pop().to_string(); self.push(BcValue::Str(pll_runtime::pll_db_get(&k).unwrap_or_default())); }
            6 => { let v = self.pop().to_string(); pll_runtime::pll_print(&v); }
            10 => { let b = self.pop().to_string(); let a = self.pop().to_string(); self.push(BcValue::Str(format!("{}{}", a, b))); }
            11 => { let v = self.pop().as_str().ok_or("str_length requires string")?.to_string(); self.push(BcValue::Num(v.chars().count() as f64)); }
            12 => { let end = self.pop().as_num().ok_or("str_slice requires number")?; let start = self.pop().as_num().ok_or("str_slice requires number")?; let s = self.pop().as_str().ok_or("str_slice requires string")?.to_string(); self.push(BcValue::Str(pll_runtime::str_slice(&s, start, end))); }
            14 => { let s = self.pop().to_string(); self.push(BcValue::Num(pll_runtime::str_to_num(&s))); }
            15 => { let n = self.pop().as_num().ok_or("str_from_num requires number")?; self.push(BcValue::Str(pll_runtime::str_from_num(n))); }
            16 => { let p = self.pop().to_string(); let s = self.pop().to_string(); self.push(BcValue::Bool(pll_runtime::str_starts_with(&s, &p))); }
            18 => { let s = self.pop().to_string(); self.push(BcValue::Str(s.to_uppercase())); }
            20 => { let len = if let BcValue::List(list) = self.pop() { list.len() as f64 } else { 0.0 }; self.push(BcValue::Num(len)); }
            21 => { let idx = self.pop().as_num().ok_or("list_get requires number")? as usize; if let BcValue::List(items) = self.pop() { self.push(items.get(idx).cloned().unwrap_or(BcValue::Nil)); } else { return Err("list_get requires list".to_string()); } }
            22 => { let item = self.pop(); let mut items = if let BcValue::List(list) = self.pop() { (*list).clone() } else { vec![] }; items.push(item); self.push(BcValue::List(Arc::new(items))); }
            40 => { let args: Vec<BcValue> = pll_runtime::pll_args().into_iter().map(BcValue::Str).collect(); self.push(BcValue::List(Arc::new(args))); }
            41 => { let path = self.pop().to_string(); let content = pll_runtime::pll_read_file(&path).unwrap_or_default(); self.push(BcValue::Str(content)); }
            42 => { let content = self.pop().to_string(); let path = self.pop().to_string(); let _ = pll_runtime::pll_write_file(&path, &content); self.push(BcValue::Nil); }
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
