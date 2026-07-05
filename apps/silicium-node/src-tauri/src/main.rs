#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    if std::env::args().any(|arg| arg == "--supervisor") {
        std::process::exit(silicium_node_lib::run_supervisor_cli());
    }
    silicium_node_lib::run();
}
