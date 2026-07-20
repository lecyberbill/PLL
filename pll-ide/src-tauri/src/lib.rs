mod db;
mod commands {
    pub mod projects;
    pub mod fs_git;
    pub mod llm;
    pub mod pll_exec;
    pub mod agentic;
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![
        commands::projects::list_projects,
        commands::projects::create_project,
        commands::projects::get_project,
        commands::projects::delete_project,
        commands::fs_git::list_project_files,
        commands::fs_git::get_project_file,
        commands::fs_git::write_project_file,
        commands::fs_git::delete_project_file,
        commands::fs_git::rename_project_file,
        commands::fs_git::get_git_status,
        commands::fs_git::git_commit,
        commands::fs_git::git_init,
        commands::fs_git::git_remote,
        commands::fs_git::git_push,
        commands::fs_git::git_pull,
        commands::fs_git::git_log,
        commands::fs_git::git_diff,
        commands::fs_git::git_show,
        commands::llm::chat_completion,
        commands::pll_exec::run_pll_code,
        commands::agentic::list_sessions,
        commands::agentic::create_session,
        commands::agentic::get_session,
        commands::agentic::archive_session,
        commands::agentic::get_conversations,
        commands::agentic::save_message
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
