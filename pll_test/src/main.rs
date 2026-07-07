pub mod test {
    use pll_runtime::*;
    use serde::{{Serialize, Deserialize}};

    pub fn run() {
        pll_render(&"hello from PLL bytecode".to_string());
    }
}

fn main() { test::run(); }
