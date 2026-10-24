use super::{
    append_app_log, configured_node_service_running, migrate_configured_node_autostart,
    restart_configured_node_service, start_configured_node_service, stop_configured_node_service,
};
use std::{
    sync::atomic::{AtomicBool, Ordering},
    thread,
};
use tauri::{
    menu::{Menu, MenuItemBuilder, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    App, AppHandle, Manager, Wry,
};

const OPEN_ID: &str = "tray-open";
const STATUS_ID: &str = "tray-status";
const START_ID: &str = "tray-start";
const STOP_ID: &str = "tray-stop";
const RESTART_ID: &str = "tray-restart";
const QUIT_ID: &str = "tray-quit";
static SERVICE_ACTION_RUNNING: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Copy)]
enum ServiceAction {
    Start,
    Stop,
    Restart,
}

pub(super) fn setup(app: &mut App<Wry>, background: bool) -> tauri::Result<()> {
    let open = MenuItemBuilder::with_id(OPEN_ID, "Ouvrir Silicium Node").build(app)?;
    let status = MenuItemBuilder::with_id(STATUS_ID, status_text())
        .enabled(false)
        .build(app)?;
    let start = MenuItemBuilder::with_id(START_ID, "Démarrer le service").build(app)?;
    let stop = MenuItemBuilder::with_id(STOP_ID, "Arrêter le service").build(app)?;
    let restart = MenuItemBuilder::with_id(RESTART_ID, "Redémarrer le service").build(app)?;
    let quit = MenuItemBuilder::with_id(QUIT_ID, "Quitter l’application").build(app)?;
    let separator_a = PredefinedMenuItem::separator(app)?;
    let separator_b = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(
        app,
        &[
            &open,
            &status,
            &separator_a,
            &start,
            &stop,
            &restart,
            &separator_b,
            &quit,
        ],
    )?;

    let status_for_menu = status.clone();
    let mut tray = TrayIconBuilder::with_id("silicium-node")
        .menu(&menu)
        .tooltip("Silicium Node")
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            OPEN_ID => show_main_window(app),
            START_ID => run_service_action(status_for_menu.clone(), ServiceAction::Start),
            STOP_ID => run_service_action(status_for_menu.clone(), ServiceAction::Stop),
            RESTART_ID => run_service_action(status_for_menu.clone(), ServiceAction::Restart),
            QUIT_ID => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                show_main_window(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon().cloned() {
        tray = tray.icon(icon);
    }
    tray.build(app)?;

    if background {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.hide();
        }
        thread::spawn(|| {
            if let Err(error) = start_configured_node_service() {
                let _ = append_app_log(&format!("tray_background_start_failed: {error}\n"));
            }
        });
    } else {
        thread::spawn(|| {
            // Migrate existing installations whose scheduled task still launches
            // the legacy supervisor-only mode.
            let _ = migrate_configured_node_autostart();
        });
    }
    Ok(())
}

fn run_service_action(status: tauri::menu::MenuItem<Wry>, action: ServiceAction) {
    if SERVICE_ACTION_RUNNING.swap(true, Ordering::AcqRel) {
        return;
    }
    thread::spawn(move || {
        let _ = status.set_text(match action {
            ServiceAction::Start => "État : démarrage…",
            ServiceAction::Stop => "État : arrêt…",
            ServiceAction::Restart => "État : redémarrage…",
        });
        let result = match action {
            ServiceAction::Start => start_configured_node_service(),
            ServiceAction::Stop => stop_configured_node_service(),
            ServiceAction::Restart => restart_configured_node_service(),
        };
        if let Err(error) = result {
            let _ = append_app_log(&format!("tray_service_action_failed: {error}\n"));
            let _ = status.set_text(format!("État : erreur ({error})"));
        } else {
            let _ = status.set_text(status_text());
        }
        SERVICE_ACTION_RUNNING.store(false, Ordering::Release);
    });
}

fn status_text() -> &'static str {
    if configured_node_service_running() {
        "État : service démarré"
    } else {
        "État : service arrêté"
    }
}

fn show_main_window(app: &AppHandle<Wry>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}
