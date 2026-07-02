
pub type SpanId = u32;

#[derive(Debug, Clone, PartialEq)]
pub struct Position {
    pub line: usize,
    pub column: usize,
    pub offset: u32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Span {
    pub start: Position,
    pub end: Position,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Spanned<T> {
    pub value: T,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Token {
    Ident(String), Num(f64), Str(String), Bool(bool),
    Plus, Minus, Star, Slash, Percent,
    Eq, Neq, Gt, Lt, Gte, Lte, Assign,
    And, Or, Not, Colon, Comma, Dot, Arrow, FatArrow,
    LParen, RParen, LBrace, RBrace, LBracket, RBracket,
    Fn, Return, If, Else, While, ForEach, In, Import,
    V, Render, Emit, Send, Recv, Print,
    T, P, Agent, On, Cap, Contract, Ui, Route, Par, Join, Fork,
    Converge, MetaStart, MetaEnd,
    TypeStr, TypeNum, TypeBool, TypeList, TypeRecord, TypeEvent,
    Newline, End,
}

impl Token {
    pub fn kind_name(&self) -> &str {
        match self {
            Token::Ident(_) => "ident", Token::Num(_) => "num",
            Token::Str(_) => "str", Token::Bool(_) => "bool",
            Token::Plus => "+", Token::Minus => "-",
            Token::Star => "*", Token::Slash => "/",
            _ => "?",
        }
    }
}

pub type ProgramMetaId = u32;

#[derive(Debug, Clone)]
pub struct ProgramMeta {
    pub zone: String,
    pub lambda: f64,
    pub agent_id: Option<ProgramMetaId>,
}

#[derive(Debug, Clone)]
pub struct Program {
    pub header: ProgramMeta,
    pub statements: Vec<Spanned<Stmt>>,
}

#[derive(Debug, Clone)]
pub enum Stmt {
    VarDecl(VarDecl),
    FnDecl(FnDecl),
    TypeDecl(TypeDecl),
    ProtocolDecl(ProtocolDecl),
    AgentDecl(AgentDecl),
    CapDecl(CapDecl),
    ContractDecl(ContractDecl),
    Render(Spanned<Expr>),
    Emit(Spanned<Expr>),
    Send(Spanned<Expr>),
    Recv(VarDecl),
    Print(Spanned<Expr>),
    DbSet { key: Spanned<Expr>, value: Spanned<Expr> },
    If(If),
    While(While),
    ForEach(ForEach),
    Return(Spanned<Expr>),
    Import(String),
    Ui(String),
    Route { path: String, body: Vec<Spanned<Stmt>> },
    Par(Vec<Vec<Spanned<Stmt>>>),
    Join { target: String, body: Vec<Spanned<Stmt>> },
    Fork(Vec<ForkBranch>),
    Converge(Converge),
    MetaExec(Spanned<Expr>),
    Assign { name: String, value: Spanned<Expr> },
    Expr(Spanned<Expr>),
}

#[derive(Debug, Clone)]
pub struct VarDecl {
    pub name: String,
    pub raw_text: Option<String>,
    pub init: Option<Spanned<Expr>>,
    pub provenance: Option<String>,
}

#[derive(Debug, Clone)]
pub struct FnDecl {
    pub name: String,
    pub params: Vec<Field>,
    pub ret_type: TypeRef,
    pub body: Vec<Spanned<Stmt>>,
}

#[derive(Debug, Clone)]
pub struct TypeDecl {
    pub name: String,
    pub fields: Vec<Field>,
}

#[derive(Debug, Clone)]
pub struct Field {
    pub name: String,
    pub type_ref: TypeRef,
    pub optional: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub enum TypeRef {
    Named(String), Num, Str, Bool, List(Box<TypeRef>),
    Record(Vec<(String, TypeRef)>), Event, Any,
}

impl Default for TypeRef {
    fn default() -> Self { TypeRef::Any }
}

#[derive(Debug, Clone)]
pub struct ProtocolDecl {
    pub name: String,
    pub msgs: Vec<ProtocolMsg>,
    pub constraints: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct ProtocolMsg {
    pub name: String,
    pub fields: Vec<Field>,
}

#[derive(Debug, Clone)]
pub struct AgentDecl {
    pub name: String,
    pub protocol: String,
    pub state: Option<AgentState>,
    pub handlers: Vec<Handler>,
}

#[derive(Debug, Clone)]
pub struct AgentState {
    pub belief: String,
    pub source: String,
    pub persistent: bool,
}

#[derive(Debug, Clone)]
pub struct Handler {
    pub msg_name: String,
    pub body: Vec<Spanned<Stmt>>,
}

#[derive(Debug, Clone)]
pub struct CapDecl {
    pub name: String,
    pub inputs: Vec<Field>,
    pub outputs: Vec<Field>,
    pub cost: Option<f64>,
    pub requires: Option<String>,
    pub safety: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct ContractDecl {
    pub name: String,
    pub params: Vec<String>,
    pub pre: Vec<String>,
    pub post: Vec<String>,
    pub invariant: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct If {
    pub condition: Spanned<Expr>,
    pub then_body: Vec<Spanned<Stmt>>,
    pub else_body: Option<Vec<Spanned<Stmt>>>,
}

#[derive(Debug, Clone)]
pub struct While {
    pub condition: Spanned<Expr>,
    pub body: Vec<Spanned<Stmt>>,
}

#[derive(Debug, Clone)]
pub struct ForEach {
    pub var: String,
    pub iter: Spanned<Expr>,
    pub body: Vec<Spanned<Stmt>>,
}

#[derive(Debug, Clone)]
pub struct ForkBranch {
    pub condition: String,
    pub confidence: f64,
    pub body: Vec<Spanned<Stmt>>,
}

#[derive(Debug, Clone)]
pub struct Converge {
    pub target: f64,
    pub patience: usize,
    pub max_steps: usize,
    pub strategies: Vec<String>,
    pub conditions: Vec<String>,
}

#[derive(Debug, Clone)]
pub enum Expr {
    Literal(Literal),
    Ident(String),
    Binary(BinaryOp, Box<Spanned<Expr>>, Box<Spanned<Expr>>),
    Unary(UnaryOp, Box<Spanned<Expr>>),
    Call(String, Vec<Spanned<Expr>>),
    Member(Box<Spanned<Expr>>, String),
    Index(Box<Spanned<Expr>>, Box<Spanned<Expr>>),
    List(Vec<Spanned<Expr>>),
    Record(String, Vec<(String, Spanned<Expr>)>),
    FieldAccess { record: Box<Spanned<Expr>>, field: String },
    Belief(String),
    SemanticTransform { input: Box<Spanned<Expr>>, target_type: String, contract: Option<String> },
    SemanticSimilarity(Box<Spanned<Expr>>, Box<Spanned<Expr>>),
    BeliefPropagation(Box<Spanned<Expr>>, Box<Spanned<Expr>>),
    Merge(Vec<Spanned<Expr>>),
    MergeWith { inputs: Vec<Spanned<Expr>>, instruction: String, threshold: f64 },
    MetaString(String),
}

#[derive(Debug, Clone)]
pub enum Literal {
    Num(f64), Str(String), Bool(bool), Nil,
}

#[derive(Debug, Clone)]
pub enum BinaryOp {
    Add, Sub, Mul, Div, Mod,
    Eq, Neq, Gt, Lt, Gte, Lte,
    And, Or,
}

#[derive(Debug, Clone)]
pub enum UnaryOp { Neg, Not }
