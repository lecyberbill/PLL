use crate::db;
use crate::commands::projects::get_project;
use serde::{Serialize, Deserialize};
use std::fs;
use std::path::PathBuf;
use std::process::Command;

#[derive(Serialize, Deserialize, Debug)]
pub struct GitStatusResponse {
    pub is_repo: bool,
    pub branch: String,
    pub remote: String,
    pub ahead: usize,
    pub behind: usize,
    pub clean: bool,
    pub staged: Vec<String>,
    pub modified: Vec<String>,
    pub deleted: Vec<String>,
    pub untracked: Vec<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct GitLogEntry {
    pub hash: String,
    pub author: String,
    pub date: String,
    pub message: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct GitDiffResponse {
    pub has_diff: bool,
    pub files: Vec<GitFileDiff>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct GitFileDiff {
    pub path: String,
    pub diff: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct FileInfo {
    pub path: String,
    pub content: String,
    pub mode: String,
    pub size: usize,
}

fn get_project_disk_path(project_id: i64) -> Result<Option<PathBuf>, String> {
    let p = get_project(project_id)?;
    if p.disk_path.is_empty() {
        Ok(None)
    } else {
        Ok(Some(PathBuf::from(p.disk_path)))
    }
}

// ---- FILESYSTEM COMMANDS ----

#[tauri::command]
pub fn list_project_files(project_id: i64) -> Result<Vec<String>, String> {
    if let Some(pdir) = get_project_disk_path(project_id)? {
        if !pdir.exists() {
            return Ok(Vec::new());
        }
        let mut files = Vec::new();
        fn walk_dir(dir: &std::path::Path, root: &std::path::Path, files: &mut Vec<String>) {
            if let Ok(entries) = fs::read_dir(dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
                    if name == ".git" || name == ".venv" || name == "node_modules" || name == "target" || name == "__pycache__" {
                        continue;
                    }
                    if path.is_file() {
                        if let Ok(rel) = path.strip_prefix(root) {
                            if let Some(s) = rel.to_str() {
                                files.push(s.replace("\\", "/"));
                            }
                        }
                    } else if path.is_dir() {
                        walk_dir(&path, root, files);
                    }
                }
            }
        }
        walk_dir(&pdir, &pdir, &mut files);
        Ok(files)
    } else {
        let conn = db::get_connection().map_err(|e| e.to_string())?;
        let mut stmt = conn
            .prepare("SELECT path FROM artifacts WHERE project_id = ?1")
            .map_err(|e| e.to_string())?;
        let rows = stmt
            .query_map([project_id], |row| row.get::<_, String>(0))
            .map_err(|e| e.to_string())?;
        let mut list = Vec::new();
        for r in rows {
            list.push(r.map_err(|e| e.to_string())?);
        }
        Ok(list)
    }
}

#[tauri::command]
pub fn get_project_file(project_id: i64, path: String) -> Result<FileInfo, String> {
    if let Some(pdir) = get_project_disk_path(project_id)? {
        let fpath = pdir.join(&path);
        if !fpath.exists() {
            return Err("Fichier non trouvé".to_string());
        }
        let content = fs::read_to_string(&fpath).unwrap_or_default();
        Ok(FileInfo {
            path,
            content,
            mode: "disk".to_string(),
            size: fpath.metadata().map(|m| m.len() as usize).unwrap_or(0),
        })
    } else {
        let conn = db::get_connection().map_err(|e| e.to_string())?;
        let mut stmt = conn
            .prepare("SELECT content FROM artifacts WHERE project_id = ?1 AND path = ?2")
            .map_err(|e| e.to_string())?;
        let content: String = stmt
            .query_row([project_id.to_string(), path.clone()], |row| row.get(0))
            .map_err(|_| "Fichier non trouvé en BDD".to_string())?;
        let size = content.len();
        Ok(FileInfo {
            path,
            content,
            mode: "db".to_string(),
            size,
        })
    }
}

#[tauri::command]
pub fn write_project_file(project_id: i64, path: String, content: String) -> Result<(), String> {
    if let Some(pdir) = get_project_disk_path(project_id)? {
        let fpath = pdir.join(&path);
        if let Some(parent) = fpath.parent() {
            let _ = fs::create_dir_all(parent);
        }
        fs::write(fpath, content).map_err(|e| e.to_string())?;
        Ok(())
    } else {
        let conn = db::get_connection().map_err(|e| e.to_string())?;
        conn.execute(
            "INSERT INTO artifacts (project_id, path, content, updated_at) VALUES (?1, ?2, ?3, CURRENT_TIMESTAMP)
             ON CONFLICT(project_id, path) DO UPDATE SET content=?3, updated_at=CURRENT_TIMESTAMP",
            rusqlite::params![project_id, path, content],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }
}

#[tauri::command]
pub fn delete_project_file(project_id: i64, path: String) -> Result<(), String> {
    if let Some(pdir) = get_project_disk_path(project_id)? {
        let fpath = pdir.join(&path);
        if fpath.exists() {
            let _ = fs::remove_file(fpath);
        }
        Ok(())
    } else {
        let conn = db::get_connection().map_err(|e| e.to_string())?;
        conn.execute(
            "DELETE FROM artifacts WHERE project_id = ?1 AND path = ?2",
            [project_id.to_string(), path],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }
}

#[tauri::command]
pub fn rename_project_file(project_id: i64, old_path: String, new_path: String) -> Result<(), String> {
    if let Some(pdir) = get_project_disk_path(project_id)? {
        let old_fp = pdir.join(&old_path);
        let new_fp = pdir.join(&new_path);
        if !old_fp.exists() {
            return Err("Fichier source manquant".to_string());
        }
        if let Some(parent) = new_fp.parent() {
            let _ = fs::create_dir_all(parent);
        }
        fs::rename(old_fp, new_fp).map_err(|e| e.to_string())?;
        Ok(())
    } else {
        let conn = db::get_connection().map_err(|e| e.to_string())?;
        conn.execute(
            "UPDATE artifacts SET path = ?3, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?1 AND path = ?2",
            [project_id.to_string(), old_path, new_path],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }
}

// ---- GIT COMMANDS ----

fn run_git_cmd(dir: &std::path::Path, args: &[&str]) -> Result<(String, String, bool), String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(dir)
        .output()
        .map_err(|e| format!("Impossible de lancer git : {}", e))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    Ok((stdout, stderr, output.status.success()))
}

#[tauri::command]
pub fn get_git_status(project_id: i64) -> Result<GitStatusResponse, String> {
    let pdir = match get_project_disk_path(project_id)? {
        Some(d) => d,
        None => return Ok(GitStatusResponse {
            is_repo: false, branch: "".to_string(), remote: "".to_string(),
            ahead: 0, behind: 0, clean: true,
            staged: vec![], modified: vec![], deleted: vec![], untracked: vec![]
        })
    };

    if !pdir.join(".git").exists() {
        return Ok(GitStatusResponse {
            is_repo: false, branch: "".to_string(), remote: "".to_string(),
            ahead: 0, behind: 0, clean: true,
            staged: vec![], modified: vec![], deleted: vec![], untracked: vec![]
        });
    }

    let (branch_out, _, _) = run_git_cmd(&pdir, &["rev-parse", "--abbrev-ref", "HEAD"])?;
    let branch = branch_out.trim().to_string();

    let (remote_out, _, _) = run_git_cmd(&pdir, &["remote", "get-url", "origin"])?;
    let remote = remote_out.trim().to_string();

    // Check status
    let (status_out, _, _) = run_git_cmd(&pdir, &["status", "--porcelain"])?;
    let mut staged = Vec::new();
    let mut modified = Vec::new();
    let mut deleted = Vec::new();
    let mut untracked = Vec::new();

    for line in status_out.lines() {
        if line.len() < 4 { continue; }
        let code = &line[0..2];
        let file_path = line[3..].trim().to_string();
        match code {
            "M " | "A " | "D " | "R " => staged.push(file_path),
            " M" => modified.push(file_path),
            " D" => deleted.push(file_path),
            "??" => untracked.push(file_path),
            _ => modified.push(file_path),
        }
    }

    let clean = staged.is_empty() && modified.is_empty() && deleted.is_empty() && untracked.is_empty();

    Ok(GitStatusResponse {
        is_repo: true,
        branch,
        remote,
        ahead: 0,
        behind: 0,
        clean,
        staged,
        modified,
        deleted,
        untracked,
    })
}

#[tauri::command]
pub fn git_commit(project_id: i64, message: String, auto_message: Option<bool>) -> Result<String, String> {
    let pdir = get_project_disk_path(project_id)?.ok_or("Le projet n'est pas lié à un dossier sur disque")?;
    let _ = run_git_cmd(&pdir, &["add", "."])?;
    let msg = if auto_message.unwrap_or(false) || message.is_empty() {
        "Auto-commit from PLL IDE".to_string()
    } else {
        message
    };
    let (stdout, stderr, ok) = run_git_cmd(&pdir, &["commit", "-m", &msg])?;
    if ok {
        Ok(stdout)
    } else {
        Err(stderr)
    }
}

#[tauri::command]
pub fn git_init(project_id: i64) -> Result<(), String> {
    let pdir = get_project_disk_path(project_id)?.ok_or("Le projet n'est pas lié à un dossier sur disque")?;
    let (_, _, ok) = run_git_cmd(&pdir, &["init"])?;
    if ok {
        Ok(())
    } else {
        Err("Erreur d'initialisation du dépôt git".to_string())
    }
}

#[tauri::command]
pub fn git_remote(project_id: i64, url: String) -> Result<(), String> {
    let pdir = get_project_disk_path(project_id)?.ok_or("Le projet n'est pas lié à un dossier sur disque")?;
    let _ = run_git_cmd(&pdir, &["remote", "remove", "origin"]);
    let (_, stderr, ok) = run_git_cmd(&pdir, &["remote", "add", "origin", &url])?;
    if ok {
        Ok(())
    } else {
        Err(stderr)
    }
}

#[tauri::command]
pub fn git_push(project_id: i64) -> Result<String, String> {
    let pdir = get_project_disk_path(project_id)?.ok_or("Le projet n'est pas lié à un dossier sur disque")?;
    let (stdout, stderr, ok) = run_git_cmd(&pdir, &["push", "origin", "main"])?;
    if ok {
        Ok(stdout)
    } else {
        Err(stderr)
    }
}

#[tauri::command]
pub fn git_pull(project_id: i64) -> Result<String, String> {
    let pdir = get_project_disk_path(project_id)?.ok_or("Le projet n'est pas lié à un dossier sur disque")?;
    let (stdout, stderr, ok) = run_git_cmd(&pdir, &["pull", "origin", "main"])?;
    if ok {
        Ok(stdout)
    } else {
        Err(stderr)
    }
}

#[tauri::command]
pub fn git_log(project_id: i64) -> Result<Vec<GitLogEntry>, String> {
    let pdir = get_project_disk_path(project_id)?.ok_or("Le projet n'est pas lié à un dossier sur disque")?;
    let (stdout, _, ok) = run_git_cmd(&pdir, &["log", "-n", "20", "--pretty=format:%H|%an|%ad|%s", "--date=short"])?;
    if !ok {
        return Ok(Vec::new());
    }
    let mut logs = Vec::new();
    for line in stdout.lines() {
        let parts: Vec<&str> = line.split('|').collect();
        if parts.len() >= 4 {
            logs.push(GitLogEntry {
                hash: parts[0].to_string(),
                author: parts[1].to_string(),
                date: parts[2].to_string(),
                message: parts[3..].join("|"),
            });
        }
    }
    Ok(logs)
}

#[tauri::command]
pub fn git_diff(project_id: i64) -> Result<GitDiffResponse, String> {
    let pdir = get_project_disk_path(project_id)?.ok_or("Le projet n'est pas lié à un dossier sur disque")?;
    let (stdout, _, ok) = run_git_cmd(&pdir, &["diff", "--name-only"])?;
    if !ok || stdout.trim().is_empty() {
        return Ok(GitDiffResponse { has_diff: false, files: Vec::new() });
    }
    let mut files = Vec::new();
    for line in stdout.lines() {
        let path = line.trim();
        if path.is_empty() { continue; }
        let (diff_content, _, _) = run_git_cmd(&pdir, &["diff", path])?;
        files.push(GitFileDiff {
            path: path.to_string(),
            diff: diff_content,
        });
    }
    Ok(GitDiffResponse {
        has_diff: !files.is_empty(),
        files,
    })
}

#[tauri::command]
pub fn git_show(project_id: i64, file_path: String) -> Result<String, String> {
    let pdir = get_project_disk_path(project_id)?.ok_or("Le projet n'est pas lié à un dossier sur disque")?;
    let (stdout, stderr, ok) = run_git_cmd(&pdir, &["show", &format!("HEAD:{}", file_path)])?;
    if ok {
        Ok(stdout)
    } else {
        Err(stderr)
    }
}
