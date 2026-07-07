use serde::{Serialize, Deserialize};
use std::process::Command;
use std::fs;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Debug)]
pub struct PllExecResponse {
    pub ok: bool,
    pub output: String,
    pub error: String,
}

fn find_pll_cli() -> Option<PathBuf> {
    // Look in target/release, target/debug, parent, etc.
    let paths = vec![
        PathBuf::from("../target/release/pll-cli.exe"),
        PathBuf::from("../target/release/pll-cli"),
        PathBuf::from("target/release/pll-cli.exe"),
        PathBuf::from("target/release/pll-cli"),
        PathBuf::from("../target/debug/pll-cli.exe"),
        PathBuf::from("../target/debug/pll-cli"),
        PathBuf::from("target/debug/pll-cli.exe"),
        PathBuf::from("target/debug/pll-cli"),
        PathBuf::from("./pll-cli.exe"),
        PathBuf::from("./pll-cli"),
    ];

    for path in paths {
        if path.exists() {
            return Some(path);
        }
    }
    None
}

#[tauri::command]
pub fn run_pll_code(code: String) -> Result<PllExecResponse, String> {
    let binary = find_pll_cli().ok_or_else(|| "pll-cli binary non trouvé (compiles-le d'abord avec cargo build --release)".to_string())?;

    // Create a temp file
    let temp_dir = std::env::temp_dir();
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let temp_file_path = temp_dir.join(format!("temp_exec_{}.pll", timestamp));
    
    fs::write(&temp_file_path, code).map_err(|e| format!("Erreur écriture fichier temporaire: {}", e))?;

    // Run command: pll-cli run --bc <file>
    let output = Command::new(&binary)
        .args(&["run", "--bc", temp_file_path.to_str().unwrap_or_default()])
        .output();

    // Clean up temp file
    let _ = fs::remove_file(temp_file_path);

    match output {
        Ok(out) => {
            let stdout = String::from_utf8_lossy(&out.stdout).to_string();
            let stderr = String::from_utf8_lossy(&out.stderr).to_string();
            Ok(PllExecResponse {
                ok: out.status.success(),
                output: stdout.trim().to_string(),
                error: stderr.trim().to_string(),
            })
        }
        Err(e) => Err(format!("Erreur lors de l'exécution de pll-cli: {}", e)),
    }
}
