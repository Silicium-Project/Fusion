//! Silicium desktop node launcher (Tauri backend).
//!
//! The same binary runs in three modes (see `main.rs`): the desktop app
//! ([`run`]), the background supervisor (`--supervisor`,
//! [`run_supervisor_cli`]) and the uninstall cleanup (`--cleanup`,
//! [`run_cleanup_cli`]).
//!
//! Modules share the imports and items below: each one starts with
//! `use crate::*;`, and the root glob-imports every module.

use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use chrono::{DateTime, SecondsFormat, Utc};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    cmp::Ordering,
    env,
    ffi::OsStr,
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{TcpListener, TcpStream, UdpSocket},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::State;

mod activity;
mod ai;
mod checks;
mod commands;
mod config;
mod http;
mod logging;
mod node;
mod paths;
mod process;
mod runtime;
mod service;
mod supervisor;
#[cfg(test)]
mod tests;
mod types;
mod update;

#[cfg(target_os = "windows")]
mod tray;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
use windows_sys::Win32::{
    Foundation::{CloseHandle, STILL_ACTIVE},
    System::Threading::{GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION},
};

use activity::*;
use ai::*;
use checks::*;
use config::*;
use http::*;
use logging::*;
use node::*;
use paths::*;
use process::*;
use runtime::*;
use service::*;
use supervisor::*;
use types::*;
use update::*;

pub use process::run_cleanup_cli;
pub use supervisor::run_supervisor_cli;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    install_crash_log();
    if let Err(error) = remove_legacy_runtime_assets(&managed_runtime_root()) {
        let _ = append_app_log(&format!("legacy_runtime_cleanup_failed: {error}\n"));
    }
    thread::spawn(run_background_update_loop);
    #[cfg(target_os = "windows")]
    let background = env::args().any(|argument| argument == "--background");
    let builder = tauri::Builder::default().manage(ProcessState::default());
    #[cfg(target_os = "windows")]
    let builder = builder.setup(move |app| {
        tray::setup(app, background)?;
        Ok(())
    });
    #[cfg(target_os = "windows")]
    let builder = builder.on_window_event(|window, event| {
        if let tauri::WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            let _ = window.hide();
        }
    });
    if let Err(error) = builder
        .invoke_handler(tauri::generate_handler![
            commands::start_node,
            commands::stop_node,
            commands::node_status,
            commands::check_environment,
            commands::node_activity,
            commands::node_diagnostics,
            commands::app_defaults,
            commands::update_status,
            commands::check_for_updates,
            commands::ai_tasks_status,
            commands::set_ai_tasks
        ])
        .run(tauri::generate_context!())
    {
        let _ = append_app_log(&format!("tauri_runtime_error: {error}\n"));
    }
}
