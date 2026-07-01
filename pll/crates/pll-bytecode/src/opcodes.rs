#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Opcode {
    Nop = 0, PushNum = 1, PushStr = 2, PushBool = 3, PushNil = 4,
    Pop = 5,
    Add = 10, Sub = 11, Mul = 12, Div = 13,
    Eq = 20, Neq = 21, Gt = 22, Lt = 23, Gte = 24, Lte = 25,
    And = 26, Or = 27, Not = 28,
    LoadVar = 30, StoreVar = 31,
    Jmp = 40, Jif = 41,
    Call = 50, Ret = 51,
    Builtin = 60,
    ListNew = 70, ListPush = 71, ListGet = 72, ListLen = 73,
    RecordNew = 74, RecordSet = 75, Field = 76,
    FnTable = 80, Halt = 255,
}
