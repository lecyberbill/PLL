use std::collections::HashMap;
use std::sync::Arc;
use pll_core::*;

#[derive(Debug, Clone)]
pub enum Value {
    Num(f64), Str(String), Bool(bool),
    List(Arc<Vec<Value>>),
    Record(Arc<HashMap<String, Value>>),
    Nil,
}

impl Value {
    pub fn truthy(&self) -> bool {
        match self {
            Value::Bool(b) => *b, Value::Num(n) => *n != 0.0,
            Value::Str(s) => !s.is_empty(),
            Value::List(v) => !v.is_empty(),
            Value::Record(m) => !m.is_empty(),
            Value::Nil => false,
        }
    }
    pub fn to_string(&self) -> String {
        match self {
            Value::Num(n) => n.to_string(), Value::Str(s) => s.clone(),
            Value::Bool(b) => b.to_string(),
            Value::List(items) => format!("[{}]", items.iter().map(|v| v.to_string()).collect::<Vec<_>>().join(", ")),
            Value::Record(map) => format!("{{{}}}", map.iter().map(|(k,v)| format!("{}:{}",k,v.to_string())).collect::<Vec<_>>().join(", ")),
            Value::Nil => "nil".to_string(),
        }
    }
    pub fn as_num(&self) -> Option<f64> { match self { Value::Num(n) => Some(*n), _ => None } }
}

pub struct Environment {
    pub vars: HashMap<String, Value>,
    pub fns: HashMap<String, (Vec<String>, Vec<Spanned<Stmt>>)>,
    pub types: HashMap<String, TypeDecl>,
}

impl Environment {
    pub fn new() -> Self {
        Self { vars: HashMap::new(), fns: HashMap::new(), types: HashMap::new() }
    }
}

pub fn run_program(program: &Program, env: &mut Environment) -> Result<(), String> {
    for stmt in &program.statements {
        if let Stmt::TypeDecl(t) = &stmt.value { env.types.insert(t.name.clone(), t.clone()); }
        if let Stmt::FnDecl(f) = &stmt.value { env.fns.insert(f.name.clone(), (f.params.iter().map(|p| p.name.clone()).collect(), f.body.clone())); }
    }
    for stmt in &program.statements { exec_stmt(stmt, env)?; }
    Ok(())
}

fn exec_stmt(stmt: &Spanned<Stmt>, env: &mut Environment) -> Result<(), String> {
    match &stmt.value {
        Stmt::VarDecl(v) => {
            let val = if let Some(init) = &v.init { eval_expr(init, env)? } else { Value::Nil };
            env.vars.insert(v.name.clone(), val);
            Ok(())
        }
        Stmt::FnDecl(_) | Stmt::TypeDecl(_) => Ok(()),
        Stmt::Render(e) => { let val = eval_expr(e, env)?; pll_runtime::pll_render(&val.to_string()); Ok(()) }
        Stmt::Print(e) => { let val = eval_expr(e, env)?; pll_runtime::pll_print(&val.to_string()); Ok(()) }
        Stmt::Emit(e) => { let val = eval_expr(e, env)?; pll_runtime::pll_emit(&val.to_string()); Ok(()) }
        Stmt::Send(e) => { let val = eval_expr(e, env)?; pll_runtime::pll_send(&val.to_string()); Ok(()) }
        Stmt::Recv(v) => { let msg = pll_runtime::pll_recv(); env.vars.insert(v.name.clone(), Value::Str(msg)); Ok(()) }
        Stmt::If(i) => {
            if eval_expr(&i.condition, env)?.truthy() {
                for s in &i.then_body { exec_stmt(s, env)?; }
            } else if let Some(el) = &i.else_body { for s in el { exec_stmt(s, env)?; } }
            Ok(())
        }
        Stmt::While(w) => {
            while eval_expr(&w.condition, env)?.truthy() {
                for s in &w.body { exec_stmt(s, env)?; }
            }
            Ok(())
        }
        Stmt::Return(e) => { let val = eval_expr(e, env)?; return Err(format!("__RETURN__:{}", val.to_string())); }
        Stmt::Expr(e) => { eval_expr(e, env)?; Ok(()) }
        _ => Ok(()),
    }
}

fn eval_expr(expr: &Spanned<Expr>, env: &mut Environment) -> Result<Value, String> {
    match &expr.value {
        Expr::Literal(lit) => Ok(match lit {
            Literal::Num(n) => Value::Num(*n),
            Literal::Str(s) => Value::Str(s.clone()),
            Literal::Bool(b) => Value::Bool(*b),
            Literal::Nil => Value::Nil,
        }),
        Expr::Ident(name) => Ok(env.vars.get(name).cloned().unwrap_or(Value::Nil)),
        Expr::Binary(op, left, right) => {
            let l = eval_expr(left, env)?; let r = eval_expr(right, env)?;
            Ok(match op {
                BinaryOp::Add | BinaryOp::Sub | BinaryOp::Mul | BinaryOp::Div => Value::Num(
                    l.as_num().unwrap_or(0.0) + r.as_num().unwrap_or(0.0)
                ),
                BinaryOp::Eq => Value::Bool(l.to_string() == r.to_string()),
                _ => Value::Nil,
            })
        }
        Expr::Call(name, args) => {
            let mut evaled = Vec::new();
            for a in args { evaled.push(eval_expr(a, env)?); }
            match name.as_str() {
                "render" => { if let Some(v) = evaled.last() { pll_runtime::pll_render(&v.to_string()); } Ok(Value::Nil) }
                "print" => { if let Some(v) = evaled.last() { pll_runtime::pll_print(&v.to_string()); } Ok(Value::Nil) }
                "str_concat" => Ok(Value::Str(evaled.iter().map(|v| v.to_string()).collect::<Vec<_>>().join(""))),
                "str_length" => Ok(Value::Num(evaled.first().map(|v| v.to_string().chars().count() as f64).unwrap_or(0.0))),
                "str_from_num" => Ok(Value::Str(evaled.first().map(|v| pll_runtime::str_from_num(v.as_num().unwrap_or(0.0))).unwrap_or_default())),
                "str_to_num" => Ok(Value::Num(evaled.first().map(|v| pll_runtime::str_to_num(&v.to_string())).unwrap_or(0.0))),
                "read_file" => Ok(Value::Str(pll_runtime::pll_read_file(&evaled.first().map(|v|v.to_string()).unwrap_or_default()).unwrap_or_default())),
                "write_file" => { let c = if evaled.len()>1{evaled[1].to_string()}else{String::new()}; let p = evaled[0].to_string(); let _=pll_runtime::pll_write_file(&p,&c); Ok(Value::Nil) }
                "send" => { if let Some(v)=evaled.last(){pll_runtime::pll_send(&v.to_string())} Ok(Value::Nil) }
                "recv" => Ok(Value::Str(pll_runtime::pll_recv())),
                _ => {
                    if let Some((params, body)) = env.fns.get(name) {
                        let saved = env.vars.clone();
                        for (i, val) in evaled.into_iter().enumerate() { if i < params.len() { env.vars.insert(params[i].clone(), val); } }
                        for s in body { match exec_stmt(s, env) { Err(msg) => { env.vars = saved; return if let Some(v) = msg.strip_prefix("__RETURN__:") { Ok(Value::Str(v.to_string())) } else { Err(msg) }; } Ok(()) => {} } }
                        env.vars = saved; Ok(Value::Nil)
                    } else { Ok(Value::Nil) }
                }
            }
        }
        Expr::List(items) => { let mut vals = Vec::new(); for i in items { vals.push(eval_expr(i, env)?); } Ok(Value::List(Arc::new(vals))) }
        Expr::Record(_, fields) => { let mut map = HashMap::new(); for (k, v) in fields { map.insert(k.clone(), eval_expr(v, env)?); } Ok(Value::Record(Arc::new(map))) }
        Expr::Member(obj, field) => { let v = eval_expr(obj, env)?; if let Value::Record(map) = &v { Ok(map.get(field).cloned().unwrap_or(Value::Nil)) } else { Ok(Value::Nil) } }
        _ => Ok(Value::Nil),
    }
}
