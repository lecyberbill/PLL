pub fn bc_to_pll_string(bc: &[u8]) -> String {
    let mut parts = Vec::new();
    let mut i = 0;
    while i < bc.len() {
        let op = bc[i];
        i += 1;
        match op {
            1 => { parts.push(format!("[\"1\", {}]", f64::from_le_bytes([bc[i], bc[i+1], bc[i+2], bc[i+3], bc[i+4], bc[i+5], bc[i+6], bc[i+7]]))); i += 8; }
            2 => { let len = bc[i] as usize; i += 1; let s = std::str::from_utf8(&bc[i..i+len]).unwrap_or(""); parts.push(format!("[\"2\", \"{}\"]", s)); i += len; }
            3 => { parts.push(format!("[\"3\", {}]", bc[i])); i += 1; }
            4 => { parts.push("[\"4\"]".to_string()); }
            5 => { parts.push("[\"5\"]".to_string()); }
            10 => parts.push("[\"10\"]".to_string()), 11 => parts.push("[\"11\"]".to_string()),
            12 => parts.push("[\"12\"]".to_string()), 13 => parts.push("[\"13\"]".to_string()),
            20 => parts.push("[\"20\"]".to_string()), 21 => parts.push("[\"21\"]".to_string()),
            22 => parts.push("[\"22\"]".to_string()), 23 => parts.push("[\"23\"]".to_string()),
            24 => parts.push("[\"24\"]".to_string()), 25 => parts.push("[\"25\"]".to_string()),
            26 => parts.push("[\"26\"]".to_string()), 27 => parts.push("[\"27\"]".to_string()),
            28 => parts.push("[\"28\"]".to_string()),
            30 => { let len = bc[i] as usize; i += 1; let s = std::str::from_utf8(&bc[i..i+len]).unwrap_or(""); parts.push(format!("[\"30\", \"{}\"]", s)); i += len; }
            31 => { let len = bc[i] as usize; i += 1; let s = std::str::from_utf8(&bc[i..i+len]).unwrap_or(""); parts.push(format!("[\"31\", \"{}\"]", s)); i += len; }
            40 | 41 => { let offset = i16::from_le_bytes([bc[i], bc[i+1]]); parts.push(format!("[\"{}\", {}]", op, offset)); i += 2; }
            50 => { parts.push(format!("[\"50\", {}, {}]", bc[i], bc[i+1])); i += 2; }
            51 => parts.push("[\"51\"]".to_string()),
            60 => { parts.push(format!("[\"60\", {}]", bc[i])); i += 1; }
            70 => parts.push("[\"70\"]".to_string()), 71 => parts.push("[\"71\"]".to_string()),
            72 => parts.push("[\"72\"]".to_string()), 73 => parts.push("[\"73\"]".to_string()),
            255 => parts.push("[\"255\"]".to_string()),
            _ => parts.push(format!("[{}]", op)),
        }
    }
    format!("[{}]", parts.join(", "))
}
