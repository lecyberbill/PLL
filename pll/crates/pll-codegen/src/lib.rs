use pll_core::*;

pub struct Codegen {
    module: String,
    types: Vec<TypeDecl>,
    fns: Vec<FnDecl>,
}

impl Codegen {
    pub fn new(module: &str) -> Self {
        Self { module: module.to_string(), types: Vec::new(), fns: Vec::new() }
    }

    pub fn emit_program(&mut self, program: &Program) -> String {
        let mut out = String::new();
        for stmt in &program.statements {
            match &stmt.value {
                Stmt::TypeDecl(t) => self.types.push(t.clone()),
                Stmt::FnDecl(f) => self.fns.push(f.clone()),
                _ => {}
            }
        }
        out.push_str(&format!("pub mod {} {{\n", self.module));
        out.push_str("    use pll_runtime::*;\n");
        out.push_str("    use serde::{{Serialize, Deserialize}};\n\n");
        for t in &self.types {
            let fields: Vec<String> = t.fields.iter().map(|f| {
                let ft = self.type_to_rust(&f.type_ref);
                if f.optional { format!("    pub {}: Option<{}>,", f.name, ft) }
                else { format!("    pub {}: {},", f.name, ft) }
            }).collect();
            out.push_str(&format!("#[derive(Debug, Clone, Serialize, Deserialize)]\n"));
            out.push_str(&format!("pub struct {} {{\n{}\n}}\n\n", t.name, fields.join("\n")));
        }
        out.push_str(&format!("    pub fn run() {{\n"));
        for stmt in &program.statements {
            self.emit_stmt(stmt, &mut out, 2);
        }
        out.push_str(&format!("    }}\n"));
        for f in &self.fns {
            self.emit_fn(f, &mut out);
        }
        out.push_str("}\n");
        out
    }

    fn emit_stmt(&self, stmt: &Spanned<Stmt>, out: &mut String, indent: usize) {
        let ind = "    ".repeat(indent);
        match &stmt.value {
            Stmt::VarDecl(v) => {
                if let Some(init) = &v.init { out.push_str(&format!("{}let {} = {};\n", ind, v.name, self.expr_to_rust(init))); }
            }
            Stmt::Render(e) => out.push_str(&format!("{}pll_render(&{});\n", ind, self.expr_to_rust(e))),
            Stmt::Print(e) => out.push_str(&format!("{}pll_print(&{});\n", ind, self.expr_to_rust(e))),
            Stmt::Send(e) => out.push_str(&format!("{}pll_send(&{});\n", ind, self.expr_to_rust(e))),
            Stmt::If(i) => {
                out.push_str(&format!("{}if {} {{\n", ind, self.expr_to_rust(&i.condition)));
                for s in &i.then_body { self.emit_stmt(s, out, indent + 1); }
                if let Some(el) = &i.else_body {
                    out.push_str(&format!("{}}} else {{\n", ind));
                    for s in el { self.emit_stmt(s, out, indent + 1); }
                }
                out.push_str(&format!("{}}}\n", ind));
            }
            Stmt::FnDecl(_) => {}
            _ => {}
        }
    }

    fn emit_fn(&self, f: &FnDecl, out: &mut String) {
        let params: Vec<String> = f.params.iter().map(|p| format!("{}: {}", p.name, self.type_to_rust(&p.type_ref))).collect();
        out.push_str(&format!("    pub fn {}({}) -> {} {{\n", f.name, params.join(", "), self.type_to_rust(&f.ret_type)));
        for s in &f.body { self.emit_stmt(s, out, 3); }
        out.push_str("    }\n");
    }

    fn expr_to_rust(&self, expr: &Spanned<Expr>) -> String {
        match &expr.value {
            Expr::Literal(lit) => match lit {
                Literal::Num(n) => n.to_string(),
                Literal::Str(s) => format!("\"{}\".to_string()", s.replace('"', "\\\"")),
                Literal::Bool(b) => b.to_string(),
                Literal::Nil => "String::new()".to_string(),
            },
            Expr::Ident(name) => name.clone(),
            Expr::Binary(op, left, right) => {
                let ops = match op { BinaryOp::Add => "+", BinaryOp::Sub => "-", BinaryOp::Mul => "*", BinaryOp::Div => "/", _ => "+" };
                format!("({} {} {})", self.expr_to_rust(left), ops, self.expr_to_rust(right))
            }
            Expr::Call(name, args) => {
                let a: Vec<String> = args.iter().map(|a| self.expr_to_rust(a)).collect();
                if name == "str_concat" { format!("format!(\"{{}}{{}}\", {})", a.join(", ")) }
                else { format!("{}({})", name, a.join(", ")) }
            }
            _ => "String::new()".to_string(),
        }
    }

    fn type_to_rust(&self, tr: &TypeRef) -> String {
        match tr { TypeRef::Num => "f64", TypeRef::Str => "String", TypeRef::Bool => "bool", TypeRef::Any => "String", TypeRef::Named(n) => n, _ => "String" }.to_string()
    }
}
