use crate::db;
use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Clone)]
pub struct Session {
    pub id: i64,
    pub project_id: i64,
    pub agent_type: String,
    pub status: String,
    pub generation: i32,
    pub current_state: String,
    pub objective: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct ConversationMessage {
    pub id: i64,
    pub project_id: i64,
    pub session_id: Option<i64>,
    pub role: String,
    pub content: String,
    pub created_at: String,
}

#[tauri::command]
pub fn list_sessions(project_id: i64) -> Result<Vec<Session>, String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    let mut stmt = conn
        .prepare("SELECT id, project_id, agent_type, status, generation, current_state, objective, created_at, updated_at FROM agent_sessions WHERE project_id = ?1 ORDER BY created_at DESC")
        .map_err(|e| e.to_string())?;
        
    let session_iter = stmt
        .query_map([project_id], |row| {
            Ok(Session {
                id: row.get(0)?,
                project_id: row.get(1)?,
                agent_type: row.get(2)?,
                status: row.get(3)?,
                generation: row.get(4)?,
                current_state: row.get(5)?,
                objective: row.get(6)?,
                created_at: row.get(7)?,
                updated_at: row.get(8)?,
            })
        })
        .map_err(|e| e.to_string())?;

    let mut list = Vec::new();
    for s in session_iter {
        list.push(s.map_err(|e| e.to_string())?);
    }
    Ok(list)
}

#[tauri::command]
pub fn create_session(project_id: i64) -> Result<Session, String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    
    // First, archive all other active sessions for this project
    conn.execute(
        "UPDATE agent_sessions SET status = 'archived' WHERE project_id = ?1 AND status = 'active'",
        [project_id],
    )
    .map_err(|e| e.to_string())?;

    conn.execute(
        "INSERT INTO agent_sessions (project_id, agent_type, status, generation, current_state, objective) VALUES (?1, 'primary', 'active', 0, '', '')",
        [project_id],
    )
    .map_err(|e| e.to_string())?;

    let id = conn.last_insert_rowid();
    
    let mut stmt = conn
        .prepare("SELECT id, project_id, agent_type, status, generation, current_state, objective, created_at, updated_at FROM agent_sessions WHERE id = ?1")
        .map_err(|e| e.to_string())?;
        
    let session = stmt
        .query_row([id], |row| {
            Ok(Session {
                id: row.get(0)?,
                project_id: row.get(1)?,
                agent_type: row.get(2)?,
                status: row.get(3)?,
                generation: row.get(4)?,
                current_state: row.get(5)?,
                objective: row.get(6)?,
                created_at: row.get(7)?,
                updated_at: row.get(8)?,
            })
        })
        .map_err(|e| e.to_string())?;

    Ok(session)
}

#[tauri::command]
pub fn get_session(session_id: i64) -> Result<Session, String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    let mut stmt = conn
        .prepare("SELECT id, project_id, agent_type, status, generation, current_state, objective, created_at, updated_at FROM agent_sessions WHERE id = ?1")
        .map_err(|e| e.to_string())?;
        
    let session = stmt
        .query_row([session_id], |row| {
            Ok(Session {
                id: row.get(0)?,
                project_id: row.get(1)?,
                agent_type: row.get(2)?,
                status: row.get(3)?,
                generation: row.get(4)?,
                current_state: row.get(5)?,
                objective: row.get(6)?,
                created_at: row.get(7)?,
                updated_at: row.get(8)?,
            })
        })
        .map_err(|e| e.to_string())?;

    Ok(session)
}

#[tauri::command]
pub fn archive_session(session_id: i64) -> Result<(), String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    conn.execute(
        "UPDATE agent_sessions SET status = 'archived' WHERE id = ?1",
        [session_id],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn get_conversations(session_id: i64) -> Result<Vec<ConversationMessage>, String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    let mut stmt = conn
        .prepare("SELECT id, project_id, session_id, role, content, created_at FROM conversations WHERE session_id = ?1 ORDER BY id ASC")
        .map_err(|e| e.to_string())?;
        
    let msg_iter = stmt
        .query_map([session_id], |row| {
            Ok(ConversationMessage {
                id: row.get(0)?,
                project_id: row.get(1)?,
                session_id: row.get(2)?,
                role: row.get(3)?,
                content: row.get(4)?,
                created_at: row.get(5)?,
            })
        })
        .map_err(|e| e.to_string())?;

    let mut list = Vec::new();
    for m in msg_iter {
        list.push(m.map_err(|e| e.to_string())?);
    }
    Ok(list)
}

#[tauri::command]
pub fn save_message(project_id: i64, session_id: i64, role: String, content: String) -> Result<(), String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    conn.execute(
        "INSERT INTO conversations (project_id, session_id, role, content) VALUES (?1, ?2, ?3, ?4)",
        rusqlite::params![project_id, session_id, role, content],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn run_project_command(project_id: i64, command: String, args: Vec<String>) -> Result<String, String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    let disk_path: String = conn
        .query_row(
            "SELECT disk_path FROM projects WHERE id = ?1",
            [project_id],
            |row| row.get(0),
        )
        .map_err(|e| e.to_string())?;

    #[cfg(target_os = "windows")]
    let mut cmd = {
        let mut c = std::process::Command::new("powershell");
        c.arg("-Command");
        let full_cmd = format!("{} {}", command, args.join(" "));
        c.arg(full_cmd);
        c
    };

    #[cfg(not(target_os = "windows"))]
    let mut cmd = {
        let mut c = std::process::Command::new(&command);
        c.args(args);
        c
    };

    let output = cmd
        .current_dir(disk_path)
        .output()
        .map_err(|e| e.to_string())?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    
    Ok(format!("{}\n{}", stdout, stderr))
}
