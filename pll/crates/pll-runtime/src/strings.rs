pub fn str_slice(s: &str, start: f64, end: f64) -> String {
    let chars: Vec<char> = s.chars().collect();
    let s = start as usize;
    let e = end as usize;
    if s >= chars.len() { return String::new(); }
    let e = e.min(chars.len());
    chars[s..e].iter().collect()
}

pub fn str_char_at(s: &str, idx: f64) -> String {
    s.chars().nth(idx as usize).map(|c| c.to_string()).unwrap_or_default()
}

pub fn str_to_num(s: &str) -> f64 {
    s.trim().parse().unwrap_or(0.0)
}

pub fn str_from_num(n: f64) -> String {
    if n == n.floor() && n.is_finite() {
        format!("{:.0}", n)
    } else {
        format!("{}", n)
    }
}

pub fn str_starts_with(s: &str, p: &str) -> bool {
    s.starts_with(p)
}

pub fn str_ends_with(s: &str, p: &str) -> bool {
    s.ends_with(p)
}
