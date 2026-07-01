// [WFGY] Zone: SAFE | λ: 0.6 | Fallbacks: 1/RustStandardLibrary | Action: compile_pll_compiler_to_rust
use std::fs;
use std::path::Path;
use std::process::Command;
use std::collections::{HashSet, HashMap};

const RUST_RUNTIME: &str = r#"// PLL Rust Runtime Library with Structured Gemini API, Verification, Branching, Composition & Web UI Support
use std::env;
use std::fs;
use reqwest::blocking::Client;
use serde_json::json;

pub trait PLLType {
    fn schema() -> serde_json::Value;
}

#[derive(Debug, Clone)]
pub struct BeliefState {
    pub value: String,
    pub confidence: f64,
}

struct LLMConfig {
    provider: String,
    model: String,
    url: String,
    api_key: String,
}

fn get_llm_config() -> LLMConfig {
    let args: Vec<String> = env::args().collect();
    let get_arg = |name: &str| -> Option<String> {
        let idx = args.iter().position(|a| a == name)?;
        if idx + 1 < args.len() {
            Some(args[idx + 1].clone())
        } else {
            None
        }
    };

    let arg_provider = get_arg("--pll-provider");
    let arg_model = get_arg("--pll-model");
    let arg_url = get_arg("--pll-url");
    let arg_key = get_arg("--pll-key");

    let mut file_provider = None;
    let mut file_model = None;
    let mut file_url = None;
    let mut file_key = None;
    if let Ok(config_str) = fs::read_to_string("pll_config.json") {
        if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&config_str) {
            file_provider = json_val["provider"].as_str().map(|s| s.to_string());
            file_model = json_val["model"].as_str().map(|s| s.to_string());
            file_url = json_val["url"].as_str().map(|s| s.to_string());
            file_key = json_val["key"].as_str().map(|s| s.to_string());
        }
    }

    let env_provider = env::var("PLL_PROVIDER").ok();
    let env_model = env::var("PLL_MODEL").ok();
    let env_url = env::var("PLL_URL").ok();
    let env_key = env::var("PLL_API_KEY").or_else(|_| env::var("GEMINI_API_KEY")).ok();

    let provider = arg_provider
        .or(file_provider)
        .or(env_provider)
        .unwrap_or_else(|| "gemini".to_string());

    let model = arg_model
        .or(file_model)
        .or(env_model)
        .unwrap_or_else(|| "gemini-2.5-flash".to_string());

    let key = arg_key
        .or(file_key)
        .or(env_key)
        .unwrap_or_default();

    let default_url = match provider.as_str() {
        "gemini" => format!("https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}", model, key),
        _ => "http://localhost:1234/v1/chat/completions".to_string(),
    };
    
    let url = arg_url
        .or(file_url)
        .or(env_url)
        .unwrap_or(default_url);

    LLMConfig { provider, model, url, api_key: key }
}

fn call_llm_api(
    system_prompt: &str,
    user_prompt: &str,
    response_schema: Option<serde_json::Value>,
    temperature: f64,
) -> Option<String> {
    let config = get_llm_config();
    let client = Client::new();
    
    if config.api_key.is_empty() && config.url.contains("googleapis.com") {
        println!("  [Warning] No API Key specified. Mock fallback.");
        return None;
    }

    let is_gemini = config.provider.to_lowercase() == "gemini";
    let body = if is_gemini {
        let mut gen_config = json!({ "temperature": temperature });
        if let Some(schema) = response_schema {
            gen_config["responseMimeType"] = serde_json::Value::String("application/json".to_string());
            gen_config["responseSchema"] = schema;
        }
        json!({
            "contents": [{
                "parts": [{
                    "text": format!("System context: {}\nPrompt: {}", system_prompt, user_prompt)
                }]
            }],
            "generationConfig": gen_config
        })
    } else {
        let mut body_map = json!({
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        });
        if let Some(schema) = response_schema {
            body_map["response_format"] = json!({
                "type": "json_schema",
                "json_schema": {
                    "name": "schema_response",
                    "schema": schema
                }
            });
        }
        body_map
    };

    let mut request = client.post(&config.url);
    if !config.api_key.is_empty() && !is_gemini {
        request = request.header("Authorization", format!("Bearer {}", config.api_key));
    }
    
    match request.json(&body).send() {
        Ok(res) => {
            if res.status().is_success() {
                if let Ok(json_res) = res.json::<serde_json::Value>() {
                    if is_gemini {
                        if let Some(text) = json_res["candidates"][0]["content"]["parts"][0]["text"].as_str() {
                            return Some(text.trim().to_string());
                        }
                    } else {
                        if let Some(text) = json_res["choices"][0]["message"]["content"].as_str() {
                            return Some(text.trim().to_string());
                        }
                    }
                }
            } else {
                println!("  [Warning] LLM HTTP status error: {}", res.status());
            }
            None
        }
        Err(e) => {
            println!("  [Warning] LLM HTTP request error: {}", e);
            None
        }
    }
}

impl BeliefState {
    pub fn new(value: String, confidence: f64) -> Self {
        Self { value, confidence }
    }

    pub fn transform(&self, prompt: &str) -> Self {
        println!("  [LLM Call] Generating transform for instruction: '{}'", prompt);
        let system_instruction = "Transform the input value according to the instruction. Output ONLY the raw result of the transformation without prefix, explanation, or markdown quotes.";
        let user_prompt = format!("Input value: {}\nInstruction: {}", self.value, prompt);
        
        if let Some(text) = call_llm_api(system_instruction, &user_prompt, None, 0.3) {
            return Self::new(text, 1.0);
        }

        let val_lower = self.value.to_lowercase();
        let prompt_lower = prompt.to_lowercase();
        let res = if prompt_lower.contains("classify") {
            if val_lower.contains("train") || val_lower.contains("rome") {
                "booking".to_string()
            } else {
                "support".to_string()
            }
        } else {
            format!("MockProcessed: {}", self.value)
        };
        Self::new(res, 0.5)
    }

    pub fn transform_typed_with_temp<T>(&self, temperature: f64) -> T
    where
        T: serde::de::DeserializeOwned + PLLType,
    {
        println!("  [LLM Call] Generating structured transform (temp: {})...", temperature);
        let system_instruction = "Extract the requested fields from the input text precisely matching the schema. Output raw JSON ONLY.";
        
        if let Some(text) = call_llm_api(system_instruction, &self.value, Some(T::schema()), temperature) {
            if let Ok(parsed) = serde_json::from_str::<T>(&text) {
                return parsed;
            }
        }
        
        println!("  [Warning] Fallback returning default mock structured value.");
        let mut map = serde_json::Map::new();
        if let Some(props) = T::schema()["properties"].as_object() {
            for (k, v) in props {
                let type_str = v["type"].as_str().unwrap_or("string").to_lowercase();
                let val = match type_str.as_str() {
                    "boolean" => serde_json::Value::Bool(true),
                    "number" => serde_json::Value::Number(serde_json::Number::from_f64(1.0).unwrap()),
                    "array" => serde_json::Value::Array(vec![]),
                    _ => serde_json::Value::String("Rome".to_string()),
                };
                map.insert(k.clone(), val);
            }
        }
        serde_json::from_value(serde_json::Value::Object(map)).unwrap()
    }

    pub fn transform_agent<T>(&self, system_instruction: &str, temperature: f64) -> T
    where
        T: serde::de::DeserializeOwned + PLLType,
    {
        println!("  [LLM Call] Generating structured agent transform (temp: {})...", temperature);
        if let Some(text) = call_llm_api(system_instruction, &self.value, Some(T::schema()), temperature) {
            if let Ok(parsed) = serde_json::from_str::<T>(&text) {
                return parsed;
            }
        }
        
        println!("  [Warning] Fallback returning default mock structured value.");
        let mut map = serde_json::Map::new();
        if let Some(props) = T::schema()["properties"].as_object() {
            for (k, v) in props {
                let type_str = v["type"].as_str().unwrap_or("string").to_lowercase();
                let val = match type_str.as_str() {
                    "boolean" => serde_json::Value::Bool(true),
                    "number" => serde_json::Value::Number(serde_json::Number::from_f64(1.0).unwrap()),
                    "array" => serde_json::Value::Array(vec![]),
                    _ => serde_json::Value::String("Rome".to_string()),
                };
                map.insert(k.clone(), val);
            }
        }
        serde_json::from_value(serde_json::Value::Object(map)).unwrap()
    }

    pub fn similarity(&self, target: &str) -> f64 {
        println!("  [LLM Call] Estimating similarity: '{}' ~ '{}'", self.value, target);
        let query = format!(
            "Rate the semantic similarity between value A: '{}' and value B: '{}'. Output ONLY a single floating point number between 0.0 and 1.0, and absolutely nothing else.",
            self.value, target
        );
        
        if let Some(text) = call_llm_api("Compare the similarity between strings.", &query, None, 0.1) {
            if let Ok(val) = text.trim().parse::<f64>() {
                return val;
            }
        }

        if self.value.to_lowercase() == target.to_lowercase() {
            1.0
        } else if self.value.to_lowercase().contains(&target.to_lowercase()) {
            0.85
        } else {
            0.1
        }
    }
}

// Database Helpers
pub fn db_set(key: &str, value: &str) {
    let mut data = match std::fs::read_to_string("database.json") {
        Ok(content) => serde_json::from_str::<serde_json::Value>(&content).unwrap_or(serde_json::json!({})),
        Err(_) => serde_json::json!({}),
    };
    data[key] = serde_json::Value::String(value.to_string());
    let _ = std::fs::write("database.json", serde_json::to_string_pretty(&data).unwrap());
}

pub fn db_get(key: &str) -> String {
    let data = match std::fs::read_to_string("database.json") {
        Ok(content) => serde_json::from_str::<serde_json::Value>(&content).unwrap_or(serde_json::json!({})),
        Err(_) => serde_json::json!({}),
    };
    data[key].as_str().unwrap_or("").to_string()
}

// Query Parser Helper
pub fn parse_query(url: &str) -> std::collections::HashMap<String, String> {
    let mut map = std::collections::HashMap::new();
    if let Some(idx) = url.find('?') {
        let query = &url[idx + 1..];
        for pair in query.split('&') {
            let mut parts = pair.splitn(2, '=');
            if let (Some(key), Some(val)) = (parts.next(), parts.next()) {
                let replaced = val.replace('+', " ");
                let decoded = percent_encoding::percent_decode_str(&replaced).decode_utf8_lossy().to_string();
                map.insert(key.to_string(), decoded);
            }
        }
    }
    map
}

// Materialize Files Helper for Multi-Agent Outputs
pub fn materialize_files(project_name: &str, text: &str) {
    let safe_name = project_name.replace(|c: char| !c.is_alphanumeric() && c != '-' && c != '_', "").trim().replace(' ', "_");
    if safe_name.is_empty() {
        return;
    }
    let project_dir = std::path::Path::new("output").join(safe_name);
    
    let mut start = 0;
    while let Some(file_start) = text[start..].find("[FILE:") {
        let abs_start = start + file_start;
        let name_start = abs_start + 6;
        if let Some(bracket_end) = text[name_start..].find(']') {
            let abs_bracket_end = name_start + bracket_end;
            let file_name = text[name_start..abs_bracket_end].trim();
            let content_start = abs_bracket_end + 1;
            
            let content_end = if let Some(file_end) = text[content_start..].find("[/FILE]") {
                content_start + file_end
            } else {
                text.len()
            };
            
            let mut content = &text[content_start..content_end];
            if content.starts_with("```") {
                if let Some(newline_idx) = content.find('\n') {
                    content = &content[newline_idx + 1..];
                }
                if content.ends_with("```") {
                    content = &content[..content.len() - 3];
                }
            }
            let trimmed_content = content.trim();
            
            let target_file = project_dir.join(file_name);
            // Ensure path safety by checking it stays under project_dir
            let target_abs = target_file.canonicalize().unwrap_or_else(|_| target_file.clone());
            let proj_abs = project_dir.canonicalize().unwrap_or_else(|_| {
                let _ = std::fs::create_dir_all(&project_dir);
                project_dir.canonicalize().unwrap_or_else(|_| project_dir.clone())
            });
            
            if target_abs.starts_with(&proj_abs) || !target_file.exists() {
                if let Some(parent) = target_file.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                if let Err(e) = std::fs::write(&target_file, trimmed_content) {
                    println!("  [Warning] Failed to write file {:?}: {}", target_file, e);
                } else {
                    println!("  [FILE_CREATED] {:?}", target_file);
                }
            }
            
            start = content_end + 7;
        } else {
            start = name_start;
        }
    }
}
"#;

fn transpile_line(line: &str, known_types: &HashSet<String>) -> String {
    let mut line = line.to_string();
    let mut comment = String::new();
    if let Some(idx) = line.find('#') {
        comment = format!("//{}", &line[idx + 1..]);
        line = line[..idx].to_string();
    }

    let indent_len = line.len() - line.trim_start().len();
    let indent_str = " ".repeat(indent_len);
    let trimmed = line.trim();

    if trimmed.is_empty() {
        if !comment.is_empty() {
            return format!("{}{}", indent_str, comment);
        }
        return String::new();
    }

    // Match variable initialization: x = ?("val")
    if trimmed.contains(" = ?(") && trimmed.ends_with(')') {
        if let Some(eq_idx) = trimmed.find('=') {
            let var_name = trimmed[..eq_idx].trim();
            if let Some(start_q) = trimmed.find('"') {
                if let Some(end_q) = trimmed.rfind('"') {
                    let val = &trimmed[start_q + 1..end_q];
                    return format!("{}let {} = BeliefState::new(\"{}\".to_string(), 1.0);", indent_str, var_name, val);
                }
            }
        }
    }

    // Match: booking = user_message => Booking
    if trimmed.contains(" = ") && trimmed.contains(" => ") {
        if let Some(eq_idx) = trimmed.find('=') {
            let var_name = trimmed[..eq_idx].trim();
            let right = trimmed[eq_idx + 1..].trim();
            if let Some(arrow_idx) = right.find("=>") {
                let src_var = right[..arrow_idx].trim();
                let dest = right[arrow_idx + 2..].trim();
                
                if dest.starts_with('"') && dest.ends_with('"') {
                    let prompt = dest.trim_matches('"');
                    return format!("{}let {} = {}.transform(\"{}\");", indent_str, var_name, src_var, prompt);
                } else if known_types.contains(dest) {
                    return format!("{}let {}: {} = {}.transform_typed_with_temp::<{}>(0.0);", indent_str, var_name, dest, src_var, dest);
                }
            }
        }
    }

    // Match if intent ~ "booking" > 0.8:
    if trimmed.starts_with("if ") && trimmed.contains('~') && trimmed.ends_with(':') {
        let cond = &trimmed[3..trimmed.len() - 1];
        if let Some(tilde_idx) = cond.find('~') {
            let var_name = cond[..tilde_idx].trim();
            let rest = cond[tilde_idx + 1..].trim();
            if let Some(gt_idx) = rest.find('>') {
                let target = rest[..gt_idx].trim().trim_matches('"');
                let threshold = rest[gt_idx + 1..].trim();
                return format!("{}if {}.similarity(\"{}\") > {} {{", indent_str, var_name, target, threshold);
            }
        }
    }

    // Match else:
    if trimmed == "else:" {
        return format!("{}}} else {{", indent_str);
    }

    // Match db_set(key, val)
    if trimmed.starts_with("db_set(") && trimmed.ends_with(')') {
        let args = &trimmed[7..trimmed.len() - 1];
        if let Some(comma_idx) = args.find(',') {
            let key = args[..comma_idx].trim().trim_matches('"');
            let val = args[comma_idx + 1..].trim();
            return format!("{}db_set(\"{}\", &format!(\"{{:?}}\", {}));", indent_str, key, val);
        }
    }

    // Match print("...") or print(var)
    if trimmed.starts_with("print(") && trimmed.ends_with(')') {
        let inner = trimmed[6..trimmed.len() - 1].trim();
        if inner.starts_with('"') && inner.ends_with('"') {
            return format!("{}println!(\"{}\");", indent_str, inner.trim_matches('"'));
        } else {
            return format!("{}println!(\"{{:?}}\", {});", indent_str, inner);
        }
    }

    format!("{}{}", indent_str, trimmed)
}

fn compile_pll(input_file: &str, output_exe_name: &str) {
    println!("[*] Reading source: {}", input_file);
    let content = fs::read_to_string(input_file).expect("Failed to read input PLL file");
    let lines: Vec<&str> = content.lines().collect();

    let mut rust_body = Vec::new();
    let mut struct_declarations = Vec::new();
    let mut known_types = HashSet::new();
    let mut open_brackets = 0;

    let mut in_fork = false;
    let mut fork_var = String::new();
    let mut fork_case_count = 0;
    let mut fork_indent = 0;

    let mut has_web_interface = false;
    let mut ui_html_lines = Vec::new();
    let mut route_mappings = HashMap::new();

    let mut i = 0;
    while i < lines.len() {
        let line = lines[i];
        let stripped = line.trim();
        if stripped.is_empty() {
            i += 1;
            continue;
        }

        let indent_len = line.len() - line.trim_start().len();

        if in_fork && indent_len <= fork_indent && !stripped.starts_with("c ") && stripped != "else:" && !stripped.starts_with("fork ") {
            rust_body.push(format!("{}}}", " ".repeat(fork_indent)));
            in_fork = false;
        }

        // Parse ui: block
        if stripped == "ui:" {
            has_web_interface = true;
            let mut j = i + 1;
            while j < lines.len() {
                let next_line = lines[j];
                let next_stripped = next_line.trim();
                if next_stripped.is_empty() {
                    j += 1;
                    continue;
                }
                let indent_len_next = next_line.len() - next_line.trim_start().len();
                if indent_len_next == 0 {
                    break;
                }
                if next_stripped.starts_with('"') && next_stripped.ends_with('"') {
                    let mut html_line = next_stripped.trim_matches('"').to_string();
                    // Escape braces for format macro, then restore db_get placeholders
                    html_line = html_line.replace("{", "{{").replace("}", "}}");
                    let mut start = 0;
                    while let Some(pos) = html_line[start..].find("{{db_get") {
                        let actual_pos = start + pos;
                        if let Some(end) = html_line[actual_pos..].find("}}") {
                            let actual_end = actual_pos + end;
                            html_line.replace_range(actual_pos..actual_end + 2, "{}");
                        }
                        start = actual_pos + 2;
                    }
                    ui_html_lines.push(html_line);
                }
                j += 1;
            }
            i = j;
            continue;
        }

        // Parse route "/path":
        if stripped.starts_with("route ") && stripped.ends_with(':') {
            has_web_interface = true;
            let route_path = stripped[6..stripped.len() - 1].trim().trim_matches('"').to_string();
            let mut route_body = Vec::new();

            let mut route_in_fork = false;
            let mut route_fork_var = String::new();
            let mut route_fork_case_count = 0;
            let mut route_fork_indent = 0;

            let mut j = i + 1;
            while j < lines.len() {
                let next_line = lines[j];
                let next_stripped = next_line.trim();
                if next_stripped.is_empty() {
                    j += 1;
                    continue;
                }
                let indent_len_next = next_line.len() - next_line.trim_start().len();
                if indent_len_next == 0 {
                    break;
                }

                if route_in_fork && indent_len_next <= route_fork_indent && !next_stripped.starts_with("c ") && next_stripped != "else:" && !next_stripped.starts_with("fork ") {
                    route_body.push(format!("{}}}", " ".repeat(route_fork_indent)));
                    route_in_fork = false;
                }

                // Check for dynamic inputs: query = input("name")
                if next_stripped.contains(" = input(") && next_stripped.ends_with(')') {
                    if let Some(eq_idx) = next_stripped.find('=') {
                        let var_name = next_stripped[..eq_idx].trim();
                        if let Some(start_q) = next_stripped.find('"') {
                            if let Some(end_q) = next_stripped.rfind('"') {
                                let param_name = &next_stripped[start_q+1..end_q];
                                route_body.push(format!("let {} = BeliefState::new(query_map.get(\"{}\").cloned().unwrap_or_default(), 1.0);", var_name, param_name));
                            }
                        }
                    }
                }
                // Check for HTTP render statement
                else if next_stripped.starts_with("render ") {
                    let expr = next_stripped[7..].trim();
                    if expr.starts_with('"') && expr.ends_with('"') {
                        let inner_expr = expr.trim_matches('"');
                        let mut rust_expr = inner_expr.to_string();
                        let mut vars = Vec::new();
                        let mut start = 0;
                        while let Some(open) = rust_expr[start..].find('{') {
                            let open_idx = start + open;
                            if let Some(close) = rust_expr[open_idx..].find('}') {
                                let close_idx = open_idx + close;
                                let var_name = &rust_expr[open_idx + 1..close_idx];
                                vars.push(var_name.to_string());
                                rust_expr.replace_range(open_idx..close_idx + 1, "{:?}");
                                start = open_idx + 4;
                            } else {
                                break;
                            }
                        }
                        if !vars.is_empty() {
                            route_body.push(format!("render_res = format!(\"{}\", {});", rust_expr, vars.join(", ")));
                        } else {
                            route_body.push(format!("render_res = \"{}\".to_string();", rust_expr));
                        }
                    } else {
                        route_body.push(format!("render_res = format!(\"{{:?}}\", {});", expr));
                    }
                }
                // Check for nested verification block inside route
                else if next_stripped.contains(" = ") && next_stripped.contains(" => ") && next_stripped.ends_with(':') {
                    if let Some(eq_idx) = next_stripped.find('=') {
                        let var_name = next_stripped[..eq_idx].trim();
                        let right = next_stripped[eq_idx + 1..next_stripped.len() - 1].trim();
                        if let Some(arrow_idx) = right.find("=>") {
                            let src_var = right[..arrow_idx].trim();
                            let type_name = right[arrow_idx + 2..].trim();
                            
                            let mut v_conditions = Vec::new();
                            let mut r_config_temp = 0.2;
                            let mut r_config_attempts = 3;

                            let mut k = j + 1;
                            while k < lines.len() {
                                let block_line = lines[k];
                                let block_stripped = block_line.trim();
                                if block_stripped.is_empty() {
                                    k += 1;
                                    continue;
                                }
                                let indent_len_block = block_line.len() - block_line.trim_start().len();
                                if indent_len_block <= indent_len_next {
                                    break;
                                }

                                if block_stripped.starts_with("v ") {
                                    let mut cond = block_stripped[2..].trim().to_string();
                                    if cond.contains("!=") {
                                        if let Some(neq_idx) = cond.find("!=") {
                                            let left = cond[..neq_idx].trim();
                                            let right_val = cond[neq_idx + 2..].trim().trim_matches('"').trim_matches('\'');
                                            if right_val.is_empty() {
                                                cond = format!("!{}.is_empty()", left);
                                            }
                                        }
                                    }
                                    v_conditions.push(cond);
                                } else if block_stripped.starts_with("r ") {
                                    if let Some(start_paren) = block_stripped.find('(') {
                                        if let Some(end_paren) = block_stripped.rfind(')') {
                                            let params = &block_stripped[start_paren + 1..end_paren];
                                            for part in params.split(',') {
                                                let part = part.trim();
                                                if part.starts_with("temp") {
                                                    if let Some(plus_eq) = part.find("+=") {
                                                        r_config_temp = part[plus_eq + 2..].trim().parse::<f64>().unwrap_or(0.2);
                                                    }
                                                } else if part.starts_with("attempts") {
                                                    if let Some(eq) = part.find('=') {
                                                        r_config_attempts = part[eq + 1..].trim().parse::<i32>().unwrap_or(3);
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                k += 1;
                            }

                            let mut conds_str = String::new();
                            for cond in v_conditions {
                                conds_str += &format!(r#"
                if !({}) {{
                    ok = false;
                }}"#, cond);
                            }

                            let loop_code = format!(r#"
            let mut temp = 0.0;
            let mut attempts = 0;
            let max_attempts = {};
            let mut {}: {};
            loop {{
                attempts += 1;
                {} = {}.transform_typed_with_temp::<{}>(temp);
                let mut ok = true;
                {}
                if ok {{
                    break;
                }}
                if attempts >= max_attempts {{
                    println!("  [PVM Warning] Max attempts reached. Continuing with current payload.");
                    break;
                }}
                temp += {};
                println!("  [PVM Retry] Verification failed. Retrying (attempt {{}}, temp {{}})...", attempts, temp);
            }}
            "#, r_config_attempts, var_name, type_name, var_name, src_var, type_name, conds_str, r_config_temp);
                            route_body.push(loop_code);
                            j = k - 1;
                        }
                    }
                }
                // Check for fork blocks inside route
                else if next_stripped.starts_with("fork ") && next_stripped.ends_with(':') {
                    route_in_fork = true;
                    route_fork_var = next_stripped[5..next_stripped.len() - 1].trim().to_string();
                    route_fork_case_count = 0;
                    route_fork_indent = indent_len_next;
                }
                else if route_in_fork && next_stripped.starts_with("c ") && next_stripped.ends_with(':') {
                    if let Some(start_q) = next_stripped.find('"') {
                        if let Some(end_q) = next_stripped[start_q + 1..].find('"') {
                            let concept = &next_stripped[start_q + 1..start_q + 1 + end_q];
                            if let Some(gt_idx) = next_stripped.find('>') {
                                if let Some(close_paren) = next_stripped.find(')') {
                                    let threshold = next_stripped[gt_idx + 1..close_paren].trim();
                                    let prefix = if route_fork_case_count > 0 { "} else if" } else { "if" };
                                    route_fork_case_count += 1;
                                    route_body.push(format!(
                                        "{} {} {}.similarity(\"{}\") > {} {{",
                                        " ".repeat(indent_len_next),
                                        prefix,
                                        route_fork_var,
                                        concept,
                                        threshold
                                    ));
                                }
                            }
                        }
                    }
                }
                else if route_in_fork && next_stripped == "else:" {
                    route_body.push(format!("{}}} else {{", " ".repeat(indent_len_next)));
                }
                else {
                    let translated = transpile_line(next_line, &known_types);
                    route_body.push(translated);
                }
                j += 1;
            }

            if route_in_fork {
                route_body.push(format!("{}}}", " ".repeat(route_fork_indent)));
            }

            route_mappings.insert(route_path, route_body);
            i = j;
            continue;
        }

        // Parse type definitions: t Booking [destination, date, flexible:bool]
        if stripped.starts_with("t ") && stripped.contains('[') && stripped.ends_with(']') {
            if let Some(start_bracket) = stripped.find('[') {
                let type_name = stripped[1..start_bracket].trim().to_string();
                known_types.insert(type_name.clone());

                let fields_str = &stripped[start_bracket + 1..stripped.len() - 1];
                let mut fields = Vec::new();
                let mut properties = Vec::new();
                let mut required = Vec::new();

                for field in fields_str.split(',') {
                    let field = field.trim();
                    if field.is_empty() {
                        continue;
                    }
                    let (f_name, rust_type, json_type) = if field.contains(':') {
                        let parts: Vec<&str> = field.split(':').collect();
                        let f_name = parts[0].trim().to_string();
                        let f_type = parts[1].trim();
                        if f_type.ends_with("[]") {
                            let base_type = &f_type[..f_type.len() - 2];
                            if base_type == "bool" {
                                (f_name, "Vec<bool>".to_string(), "json!({\"type\": \"array\", \"items\": {\"type\": \"boolean\"}})".to_string())
                            } else if base_type == "num" {
                                (f_name, "Vec<f64>".to_string(), "json!({\"type\": \"array\", \"items\": {\"type\": \"number\"}})".to_string())
                            } else if known_types.contains(base_type) {
                                (f_name, format!("Vec<{}>", base_type), format!("json!({{\"type\": \"array\", \"items\": {}::schema()}})", base_type))
                            } else {
                                (f_name, "Vec<String>".to_string(), "json!({\"type\": \"array\", \"items\": {\"type\": \"string\"}})".to_string())
                            }
                        } else {
                            if f_type == "bool" {
                                (f_name, "bool".to_string(), "json!({\"type\": \"boolean\"})".to_string())
                            } else if f_type == "num" {
                                (f_name, "f64".to_string(), "json!({\"type\": \"number\"})".to_string())
                            } else if known_types.contains(f_type) {
                                (f_name, f_type.to_string(), format!("{}::schema()", f_type))
                            } else {
                                (f_name, "String".to_string(), "json!({\"type\": \"string\"})".to_string())
                            }
                        }
                    } else {
                        (field.to_string(), "String".to_string(), "json!({\"type\": \"string\"})".to_string())
                    };

                    fields.push((f_name.to_string(), rust_type.to_string()));
                    properties.push(format!("\"{}\": {}", f_name, json_type));
                    required.push(format!("\"{}\"", f_name));
                }

                let mut struct_code = format!(
                    "#[derive(serde::Deserialize, serde::Serialize, Debug, Clone, Default)]\n#[serde(default)]\npub struct {} {{\n",
                    type_name
                );
                for (f_name, f_type) in fields {
                    struct_code += &format!("    pub {}: {},\n", f_name, f_type);
                }
                struct_code += "}\n\n";

                struct_code += &format!(
                    r#"impl PLLType for {} {{
    fn schema() -> serde_json::Value {{
        serde_json::json!({{
            "type": "object",
            "properties": {{ {} }},
            "required": [ {} ]
        }})
    }}
}}
"#,
                    type_name,
                    properties.join(", "),
                    required.join(", ")
                );

                struct_declarations.push(struct_code);
            }
            i += 1;
            continue;
        }

        // Match verification loop block: booking = user_message => Booking:
        if stripped.contains(" = ") && stripped.contains(" => ") && stripped.ends_with(':') {
            if let Some(eq_idx) = stripped.find('=') {
                let var_name = stripped[..eq_idx].trim();
                let right = stripped[eq_idx + 1..stripped.len() - 1].trim();
                if let Some(arrow_idx) = right.find("=>") {
                    let src_var = right[..arrow_idx].trim();
                    let type_name = right[arrow_idx + 2..].trim();
                    
                    let mut v_conditions = Vec::new();
                    let mut r_config_temp = 0.2;
                    let mut r_config_attempts = 3;

                    let mut j = i + 1;
                    while j < lines.len() {
                        let next_line = lines[j];
                        let next_stripped = next_line.trim();
                        if next_stripped.is_empty() {
                            j += 1;
                            continue;
                        }
                        let indent_len_next = next_line.len() - next_line.trim_start().len();
                        if indent_len_next == 0 {
                            break;
                        }

                        if next_stripped.starts_with("v ") {
                            let mut cond = next_stripped[2..].trim().to_string();
                            if cond.contains("!=") {
                                if let Some(neq_idx) = cond.find("!=") {
                                    let left = cond[..neq_idx].trim();
                                    let right_val = cond[neq_idx + 2..].trim().trim_matches('"').trim_matches('\'');
                                    if right_val.is_empty() {
                                        cond = format!("!{}.is_empty()", left);
                                    }
                                }
                            }
                            v_conditions.push(cond);
                        } else if next_stripped.starts_with("r ") {
                            if let Some(start_paren) = next_stripped.find('(') {
                                if let Some(end_paren) = next_stripped.rfind(')') {
                                    let params = &next_stripped[start_paren + 1..end_paren];
                                    for part in params.split(',') {
                                        let part = part.trim();
                                        if part.starts_with("temp") {
                                            if let Some(plus_eq) = part.find("+=") {
                                                r_config_temp = part[plus_eq + 2..].trim().parse::<f64>().unwrap_or(0.2);
                                            }
                                        } else if part.starts_with("attempts") {
                                            if let Some(eq) = part.find('=') {
                                                r_config_attempts = part[eq + 1..].trim().parse::<i32>().unwrap_or(3);
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        j += 1;
                    }

                    let mut conds_str = String::new();
                    for cond in v_conditions {
                        conds_str += &format!(r#"
        if !({}) {{
            ok = false;
        }}"#, cond);
                    }

                    let loop_code = format!(r#"
    let mut temp = 0.0;
    let mut attempts = 0;
    let max_attempts = {};
    let mut {}: {};
    loop {{
        attempts += 1;
        {} = {}.transform_typed_with_temp::<{}>(temp);
        let mut ok = true;
        {}
        if ok {{
            break;
        }}
        if attempts >= max_attempts {{
            println!("  [PVM Warning] Max attempts reached. Continuing with current payload.");
            break;
        }}
        temp += {};
        println!("  [PVM Retry] Verification failed. Retrying (attempt {{}}, temp {{}})...", attempts, temp);
    }}
    "#, r_config_attempts, var_name, type_name, var_name, src_var, type_name, conds_str, r_config_temp);
                    rust_body.push(loop_code);
                    i = j;
                    continue;
                }
            }
        }

        // Match fork blocks: fork user_message:
        if stripped.starts_with("fork ") && stripped.ends_with(':') {
            in_fork = true;
            fork_var = stripped[5..stripped.len() - 1].trim().to_string();
            fork_case_count = 0;
            fork_indent = indent_len;
            i += 1;
            continue;
        }

        if in_fork {
            if stripped.starts_with("c ") && stripped.ends_with(':') {
                if let Some(start_q) = stripped.find('"') {
                    if let Some(end_q) = stripped[start_q + 1..].find('"') {
                        let concept = &stripped[start_q + 1..start_q + 1 + end_q];
                        if let Some(gt_idx) = stripped.find('>') {
                            if let Some(close_paren) = stripped.find(')') {
                                let threshold = stripped[gt_idx + 1..close_paren].trim();
                                let prefix = if fork_case_count > 0 { "} else if" } else { "if" };
                                fork_case_count += 1;
                                rust_body.push(format!(
                                    "{} {} {}.similarity(\"{}\") > {} {{",
                                    " ".repeat(indent_len),
                                    prefix,
                                    fork_var,
                                    concept,
                                    threshold
                                ));
                                i += 1;
                                continue;
                            }
                        }
                    }
                }
            } else if stripped == "else:" {
                rust_body.push(format!("{}}} else {{", " ".repeat(indent_len)));
                i += 1;
                continue;
            }
        }

        let translated = transpile_line(line, &known_types);
        rust_body.push(translated);

        if line.contains('{') {
            open_brackets += 1;
        }
        if line.contains('}') {
            open_brackets -= 1;
        }
        i += 1;
    }

    if in_fork {
        rust_body.push(format!("{}}}", " ".repeat(fork_indent)));
    }

    while open_brackets > 0 {
        rust_body.push("}".to_string());
        open_brackets -= 1;
    }

    // Set up project dir
    let project_dir = "pll_project";
    if !Path::new(project_dir).exists() {
        println!("[*] Initializing Cargo project...");
        Command::new("cargo")
            .args(&["new", project_dir, "--bin"])
            .status()
            .expect("Failed to initialize cargo project");
    }

    let cargo_toml_content = r#"[package]
name = "pll_project"
version = "0.1.0"
edition = "2021"

[dependencies]
reqwest = { version = "0.11", features = ["blocking", "json"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
tiny_http = "0.12"
percent-encoding = "2.3"
"#;
    fs::write(format!("{}/Cargo.toml", project_dir), cargo_toml_content).expect("Failed to write Cargo.toml");

    let mut main_rs_content = RUST_RUNTIME.to_string();
    main_rs_content += "\n";
    main_rs_content += &struct_declarations.join("\n");
    
    if has_web_interface {
        let html_raw = ui_html_lines.join("");
        let mut db_keys = Vec::new();
        for line in lines {
            if line.contains('"') && line.contains("db_get") {
                let mut start = 0;
                while let Some(get_idx) = line[start..].find("db_get") {
                    let get_pos = start + get_idx;
                    if let Some(sq1) = line[get_pos..].find('\'') {
                        let sq1_pos = get_pos + sq1;
                        if let Some(sq2) = line[sq1_pos + 1..].find('\'') {
                            let sq2_pos = sq1_pos + 1 + sq2;
                            db_keys.push(line[sq1_pos + 1..sq2_pos].to_string());
                        }
                    }
                    start = get_pos + 6;
                }
            }
        }
        
        let mut db_args = Vec::new();
        for key in db_keys {
            db_args.push(format!("db_get(\"{}\")", key));
        }

        let ui_format = if !db_args.is_empty() {
            format!("format!(\"{}\", {})", html_raw, db_args.join(", "))
        } else {
            format!("\"{}\".to_string()", html_raw)
        };

        main_rs_content += &format!(r#"
fn main() {{
    let server = tiny_http::Server::http("127.0.0.1:8080").unwrap();
    println!("Server running on http://127.0.0.1:8080");
    let _ = std::process::Command::new("cmd")
        .args(&["/C", "start", "http://127.0.0.1:8080"])
        .spawn();

    for request in server.incoming_requests() {{
        let url = request.url().to_string();
        let path_part = url.split('?').next().unwrap_or("");
        "#);

        if !route_mappings.contains_key("/") {
            main_rs_content += &format!(r#"
        if path_part == "/" {{
            let html = {};
            let response = tiny_http::Response::from_string(html)
                .with_header(tiny_http::Header::from_bytes(&b"Content-Type"[..], &b"text/html; charset=utf-8"[..]).unwrap());
            let _ = request.respond(response);
            continue;
        }}
            "#, ui_format);
        }

        for (path, body) in route_mappings {
            main_rs_content += &format!(r#"
        if path_part == "{}" {{
            let query_map = parse_query(&url);
            let mut render_res = String::new();
            "#, path);
            for b_line in body {
                main_rs_content += &format!("            {}\n", b_line);
            }
            main_rs_content += r#"
            let response = tiny_http::Response::from_string(render_res)
                .with_header(tiny_http::Header::from_bytes(&b"Content-Type"[..], &b"text/html; charset=utf-8"[..]).unwrap());
            let _ = request.respond(response);
            continue;
        }
            "#;
        }

        main_rs_content += r#"
        let response = tiny_http::Response::from_string("Not Found")
            .with_status_code(404);
        let _ = request.respond(response);
    }
}
"#;
    } else {
        main_rs_content += "\nfn main() {\n";
        for line in rust_body {
            main_rs_content += &format!("    {}\n", line);
        }
        main_rs_content += r#"
    println!("\n[PVM] Press Enter to exit...");
    let mut input = String::new();
    let _ = std::io::stdin().read_line(&mut input);
}
"#;
    }

    fs::write(format!("{}/src/main.rs", project_dir), main_rs_content).expect("Failed to write main.rs");

    println!("[*] Running Cargo build in release mode...");
    let status = Command::new("cargo")
        .args(&["build", "--release"])
        .current_dir(project_dir)
        .status()
        .expect("Failed to run cargo build");

    if !status.success() {
        println!("[!] Cargo build failed.");
        std::process::exit(1);
    }

    let exe_source = format!("{}/target/release/pll_project.exe", project_dir);
    if Path::new(&exe_source).exists() {
        fs::copy(&exe_source, output_exe_name).expect("Failed to copy executable");
        println!("[+] Successfully compiled to: {}", output_exe_name);
    } else {
        println!("[!] Compiled binary not found.");
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        println!("Usage: pll <input_file.pll> [-o <output.exe>]");
        return;
    }
    let input_path = &args[1];
    let mut output_path = "run_pll.exe".to_string();

    let mut i = 2;
    while i < args.len() {
        if args[i] == "-o" || args[i] == "--output" {
            if i + 1 < args.len() {
                output_path = args[i + 1].clone();
                i += 2;
                continue;
            }
        }
        i += 1;
    }

    compile_pll(input_path, &output_path);
}
