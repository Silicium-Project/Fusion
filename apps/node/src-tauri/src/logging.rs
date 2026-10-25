//! Application error log (`silicium-app.err.log`) and the panic hook.

use crate::*;

pub(crate) fn install_crash_log() {
    std::panic::set_hook(Box::new(|info| {
        let _ = append_app_log(&format!("panic: {info}\n"));
    }));
}

pub(crate) fn append_app_log(message: &str) -> Result<(), String> {
    let path = app_state_dir().join("silicium-app.err.log");
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| error.to_string())?;
    use std::io::Write;
    file.write_all(message.as_bytes())
        .map_err(|error| error.to_string())
}
