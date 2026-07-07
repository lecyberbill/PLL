use crate::db;
use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Clone)]
pub struct Project {
    pub id: i64,
    pub name: String,
    pub description: String,
    pub disk_path: String,
    pub created_at: String,
    pub updated_at: String,
}

#[tauri::command]
pub fn list_projects() -> Result<Vec<Project>, String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, disk_path, created_at, updated_at FROM projects ORDER BY updated_at DESC")
        .map_err(|e| e.to_string())?;
        
    let project_iter = stmt
        .query_map([], |row| {
            Ok(Project {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                disk_path: row.get(3)?,
                created_at: row.get(4)?,
                updated_at: row.get(5)?,
            })
        })
        .map_err(|e| e.to_string())?;

    let mut list = Vec::new();
    for p in project_iter {
        list.push(p.map_err(|e| e.to_string())?);
    }
    Ok(list)
}

#[tauri::command]
pub fn create_project(name: String, description: Option<String>, disk_path: Option<String>) -> Result<Project, String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    let desc = description.unwrap_or_default();
    let path = disk_path.unwrap_or_default();
    
    // Create actual directory on disk if requested
    if !path.is_empty() {
        std::fs::create_dir_all(&path).map_err(|e| format!("Impossible de créer le dossier sur le disque : {}", e))?;
    }

    conn.execute(
        "INSERT INTO projects (name, description, disk_path) VALUES (?1, ?2, ?3)",
        [&name, &desc, &path],
    )
    .map_err(|e| e.to_string())?;

    let id = conn.last_insert_rowid();
    
    let mut stmt = conn
        .prepare("SELECT id, name, description, disk_path, created_at, updated_at FROM projects WHERE id = ?1")
        .map_err(|e| e.to_string())?;
        
    let project = stmt
        .query_row([id], |row| {
            Ok(Project {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                disk_path: row.get(3)?,
                created_at: row.get(4)?,
                updated_at: row.get(5)?,
            })
        })
        .map_err(|e| e.to_string())?;

    Ok(project)
}

#[tauri::command]
pub fn get_project(project_id: i64) -> Result<Project, String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, disk_path, created_at, updated_at FROM projects WHERE id = ?1")
        .map_err(|e| e.to_string())?;
        
    let project = stmt
        .query_row([project_id], |row| {
            Ok(Project {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                disk_path: row.get(3)?,
                created_at: row.get(4)?,
                updated_at: row.get(5)?,
            })
        })
        .map_err(|e| e.to_string())?;

    Ok(project)
}

#[tauri::command]
pub fn delete_project(project_id: i64, keep_files: Option<bool>) -> Result<(), String> {
    let conn = db::get_connection().map_err(|e| e.to_string())?;
    
    // Read project to see disk path before deleting record
    let p = get_project(project_id)?;
    let delete_files = !keep_files.unwrap_or(true);
    
    if delete_files && !p.disk_path.is_empty() {
        let path = std::path::Path::new(&p.disk_path);
        if path.exists() {
            let _ = std::fs::remove_dir_all(path);
        }
    }

    conn.execute("DELETE FROM projects WHERE id = ?1", [project_id])
        .map_err(|e| e.to_string())?;
    Ok(())
}
