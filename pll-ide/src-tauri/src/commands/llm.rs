use serde::{Serialize, Deserialize};
use std::collections::HashSet;
use std::fs;
use std::path::Path;
use reqwest::Client;
use serde_json::json;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct LLMResponse {
    pub response: String,
    pub backend: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct CacheEntry {
    pub system_prompt: String,
    pub prompt_text: String,
    pub backend: String,
    pub response: LLMResponse,
}

fn load_env() {
    if let Ok(content) = fs::read_to_string(".env") {
        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') { continue; }
            if let Some((k, v)) = line.split_once('=') {
                std::env::set_var(k.trim(), v.trim());
            }
        }
    }
}

fn tokenize(text: &str) -> HashSet<String> {
    text.to_lowercase()
        .split(|c: char| !c.is_alphanumeric())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .collect()
}

fn calculate_jaccard(set_a: &HashSet<String>, set_b: &HashSet<String>) -> f64 {
    if set_a.is_empty() && set_b.is_empty() {
        return 1.0;
    }
    let intersection: HashSet<_> = set_a.intersection(set_b).cloned().collect();
    let union: HashSet<_> = set_a.union(set_b).cloned().collect();
    intersection.len() as f64 / union.len() as f64
}

fn lookup_cache(system_prompt: &str, messages: &[ChatMessage], backend: &str) -> Option<LLMResponse> {
    let cache_path = "llm_cache.json";
    if !Path::new(cache_path).exists() {
        return None;
    }
    let data = fs::read_to_string(cache_path).ok()?;
    let cache: Vec<CacheEntry> = serde_json::from_str(&data).unwrap_or_default();
    
    let query_text = format!("{}\n{}", system_prompt, messages.iter().map(|m| m.content.as_str()).collect::<Vec<_>>().join("\n"));
    let query_tokens = tokenize(&query_text);
    
    let mut best_match: Option<CacheEntry> = None;
    let mut best_sim = 0.0;
    let threshold = 0.85;

    for entry in cache {
        if entry.backend != backend {
            continue;
        }
        let cached_text = format!("{}\n{}", entry.system_prompt, entry.prompt_text);
        let cached_tokens = tokenize(&cached_text);
        let sim = calculate_jaccard(&query_tokens, &cached_tokens);
        if sim >= threshold && sim > best_sim {
            best_sim = sim;
            best_match = Some(entry);
        }
    }

    if let Some(entry) = best_match {
        println!("[LLM_CACHE_RUST] Semantic match found (similarity {:.2})", best_sim);
        Some(entry.response)
    } else {
        None
    }
}

fn store_cache(system_prompt: &str, messages: &[ChatMessage], backend: &str, response: LLMResponse) {
    let cache_path = "llm_cache.json";
    let mut cache: Vec<CacheEntry> = if Path::new(cache_path).exists() {
        let data = fs::read_to_string(cache_path).unwrap_or_default();
        serde_json::from_str(&data).unwrap_or_default()
    } else {
        Vec::new()
    };

    let prompt_text = messages.iter().map(|m| m.content.as_str()).collect::<Vec<_>>().join("\n");
    cache.push(CacheEntry {
        system_prompt: system_prompt.to_string(),
        prompt_text,
        backend: backend.to_string(),
        response,
    });

    if cache.len() > 500 {
        cache.remove(0);
    }

    if let Ok(data) = serde_json::to_string_pretty(&cache) {
        let _ = fs::write(cache_path, data);
    }
}

#[tauri::command]
pub async fn chat_completion(
    messages: Vec<ChatMessage>,
    system_prompt: Option<String>,
    temperature: Option<f64>,
    max_tokens: Option<usize>,
    backend: Option<String>,
) -> Result<LLMResponse, String> {
    load_env();
    
    let sys_prompt = system_prompt.unwrap_or_else(|| "You are a helpful coding assistant speaking PLL.".to_string());
    let temp = temperature.unwrap_or(0.15);
    let tokens = max_tokens.unwrap_or(4096);
    
    // Choose backend
    let default_backend = std::env::var("PLL_LLM_BACKEND").unwrap_or_else(|_| {
        if std::env::var("DP_API_KEY").is_ok() || std::env::var("Dp_API_KEY").is_ok() {
            "deepseek".to_string()
        } else {
            "lmstudio".to_string()
        }
    });
    let selected_backend = backend.unwrap_or(default_backend);

    // Check cache
    if let Some(cached) = lookup_cache(&sys_prompt, &messages, &selected_backend) {
        return Ok(cached);
    }

    let client = Client::new();
    let response_text = if selected_backend == "deepseek" {
        let api_key = std::env::var("DP_API_KEY")
            .or_else(|_| std::env::var("Dp_API_KEY"))
            .map_err(|_| "DeepSeek API key is missing (DP_API_KEY env var)".to_string())?;
        
        let mut api_messages = vec![json!({"role": "system", "content": sys_prompt})];
        for m in &messages {
            api_messages.push(json!({"role": m.role, "content": m.content}));
        }

        let body = json!({
            "model": "deepseek-chat",
            "messages": api_messages,
            "temperature": temp,
            "max_tokens": tokens,
            "stream": false
        });

        let resp = client.post("https://api.deepseek.com/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", api_key))
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("DeepSeek call failed: {}", e))?;

        if !resp.status().is_success() {
            let err_text = resp.text().await.unwrap_or_default();
            return Err(format!("DeepSeek API Error: {}", err_text));
        }

        let json_resp: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
        json_resp["choices"][0]["message"]["content"]
            .as_str()
            .ok_or_else(|| "Failed to extract DeepSeek content".to_string())?
            .to_string()
    } else {
        let lm_url = std::env::var("PLL_LM_STUDIO_URL")
            .unwrap_or_else(|_| "http://localhost:1234/v1/chat/completions".to_string());
            
        let mut api_messages = vec![json!({"role": "system", "content": sys_prompt})];
        for m in &messages {
            api_messages.push(json!({"role": m.role, "content": m.content}));
        }

        let body = json!({
            "messages": api_messages,
            "temperature": temp,
            "max_tokens": tokens,
            "stream": false
        });

        let resp = client.post(&lm_url)
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("LM Studio call failed: {}", e))?;

        if !resp.status().is_success() {
            let err_text = resp.text().await.unwrap_or_default();
            return Err(format!("LM Studio API Error: {}", err_text));
        }

        let json_resp: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
        json_resp["choices"][0]["message"]["content"]
            .as_str()
            .ok_or_else(|| "Failed to extract LM Studio content".to_string())?
            .to_string()
    };

    let result_resp = LLMResponse {
        response: response_text,
        backend: selected_backend.clone(),
    };

    store_cache(&sys_prompt, &messages, &selected_backend, result_resp.clone());
    Ok(result_resp)
}
