use std::collections::HashMap;
use pll_core::*;

#[derive(Debug)]
pub struct TypeError {
    pub message: String,
    pub span: Span,
}

pub struct TypeEnv {
    pub types: HashMap<String, TypeDecl>,
    pub fns: HashMap<String, FnDecl>,
    pub vars: HashMap<String, TypeRef>,
}

impl TypeEnv {
    pub fn new() -> Self {
        Self { types: HashMap::new(), fns: HashMap::new(), vars: HashMap::new() }
    }

    pub fn check_program(&mut self, program: &Program) -> Result<(), TypeError> {
        for stmt in &program.statements {
            self.check_stmt(stmt)?;
        }
        Ok(())
    }

    fn check_stmt(&mut self, stmt: &Spanned<Stmt>) -> Result<(), TypeError> {
        match &stmt.value {
            Stmt::TypeDecl(t) => { self.types.insert(t.name.clone(), t.clone()); Ok(()) }
            Stmt::FnDecl(f) => { self.fns.insert(f.name.clone(), f.clone()); Ok(()) }
            Stmt::VarDecl(v) => {
                if let Some(init) = &v.init {
                    let t = self.check_expr(init)?;
                    self.vars.insert(v.name.clone(), t);
                }
                Ok(())
            }
            Stmt::Assign { name, value } => {
                let t = self.check_expr(value)?;
                self.vars.insert(name.clone(), t);
                Ok(())
            }
            Stmt::Render(e) | Stmt::Emit(e) | Stmt::Print(e) | Stmt::Send(e) => {
                self.check_expr(e)?; Ok(())
            }
            Stmt::If(i) => {
                self.check_expr(&i.condition)?;
                for s in &i.then_body { self.check_stmt(s)?; }
                if let Some(el) = &i.else_body { for s in el { self.check_stmt(s)?; } }
                Ok(())
            }
            Stmt::While(w) => {
                self.check_expr(&w.condition)?;
                for s in &w.body { self.check_stmt(s)?; }
                Ok(())
            }
            Stmt::ForEach(fe) => {
                self.check_expr(&fe.iter)?;
                for s in &fe.body { self.check_stmt(s)?; }
                Ok(())
            }
            Stmt::Return(e) => { self.check_expr(e)?; Ok(()) }
            Stmt::Expr(e) => { self.check_expr(e)?; Ok(()) }
            _ => Ok(()),
        }
    }

    fn check_expr(&mut self, expr: &Spanned<Expr>) -> Result<TypeRef, TypeError> {
        match &expr.value {
            Expr::Literal(lit) => Ok(match lit {
                Literal::Num(_) => TypeRef::Num,
                Literal::Str(_) => TypeRef::Str,
                Literal::Bool(_) => TypeRef::Bool,
                Literal::Nil => TypeRef::Any,
            }),
            Expr::Ident(name) => {
                self.vars.get(name).cloned().or(Ok(TypeRef::Any))
            }
            Expr::Binary(op, left, right) => {
                let lt = self.check_expr(left)?;
                let rt = self.check_expr(right)?;
                match op {
                    BinaryOp::Add | BinaryOp::Sub | BinaryOp::Mul | BinaryOp::Div | BinaryOp::Mod => Ok(TypeRef::Num),
                    _ => Ok(TypeRef::Bool),
                }
            }
            Expr::Call(name, args) => {
                for a in args { self.check_expr(a)?; }
                self.fns.get(name).map(|f| f.ret_type.clone()).or(Ok(TypeRef::Any))
            }
            Expr::List(items) => {
                for i in items { self.check_expr(i)?; }
                Ok(TypeRef::List(Box::new(TypeRef::Any)))
            }
            Expr::Record(_, fields) => {
                for (_, v) in fields { self.check_expr(v)?; }
                Ok(TypeRef::Any)
            }
            _ => Ok(TypeRef::Any),
        }
    }
}
