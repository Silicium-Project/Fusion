//! Unit tests for the launcher backend.

use crate::*;

/// Source of every backend module, for tests that assert on embedded scripts
/// and startup wiring.
fn crate_source() -> String {
    [
        include_str!("lib.rs"),
        include_str!("activity/mod.rs"),
        include_str!("activity/machine.rs"),
        include_str!("checks.rs"),
        include_str!("commands.rs"),
        include_str!("config.rs"),
        include_str!("http.rs"),
        include_str!("logging.rs"),
        include_str!("node.rs"),
        include_str!("paths.rs"),
        include_str!("process.rs"),
        include_str!("runtime.rs"),
        include_str!("service.rs"),
        include_str!("supervisor.rs"),
        include_str!("types.rs"),
        include_str!("update/mod.rs"),
        include_str!("update/install.rs"),
        include_str!("update/manifest.rs"),
    ]
    .concat()
}

#[test]
fn node_id_is_safe_for_files_and_service_config() {
    assert_eq!(
        normalized_node_id(" pc de Thom\ninvalid "),
        "pc-de-Thom-invalid"
    );
    assert_eq!(normalized_node_id("   "), "silicium-desktop-node");
}

#[test]
fn orchestrator_url_requires_http_and_a_host() {
    assert_eq!(
        normalize_orchestrator_url(" http://127.0.0.1:46100/ ").unwrap(),
        "http://127.0.0.1:46100"
    );
    assert!(normalize_orchestrator_url("127.0.0.1:46100").is_err());
    assert!(normalize_orchestrator_url("https://").is_err());
}

#[test]
fn channel_defaults_follow_the_build_channel() {
    // Prod and dev installs share their app data: a saved default of either
    // channel is replaced by this build's own default.
    for value in [
        PROD_ORCHESTRATOR_URL,
        DEV_ORCHESTRATOR_URL,
        "https://10.77.0.1:8443/orchestrator/",
    ] {
        assert_eq!(
            migrate_legacy_orchestrator_url(value),
            default_orchestrator_url()
        );
    }
    let expected = if release_channel() == "prod" {
        PROD_ORCHESTRATOR_URL
    } else {
        DEV_ORCHESTRATOR_URL
    };
    if option_env!("SILICIUM_DEFAULT_ORCHESTRATOR_URL").is_none() {
        assert_eq!(default_orchestrator_url(), expected);
    }
    // A custom orchestrator is kept as is.
    assert_eq!(
        migrate_legacy_orchestrator_url("https://example.org/orchestrator"),
        "https://example.org/orchestrator"
    );
}

#[test]
fn legacy_public_orchestrator_urls_migrate_to_tls_proxy() {
    for value in [
        "http://213.32.68.67:46100",
        "https://213.32.68.67:46100/",
        "http://vps-910c1dbc.vps.ovh.net:46100/orchestrator",
    ] {
        assert_eq!(
            normalize_orchestrator_url(value).unwrap(),
            default_orchestrator_url()
        );
    }
    assert_eq!(
        normalize_orchestrator_url("http://127.0.0.1:46100").unwrap(),
        "http://127.0.0.1:46100"
    );
}

#[test]
fn current_process_is_detected_as_running() {
    assert!(process_is_running(std::process::id()));
}

#[cfg(target_os = "linux")]
#[test]
fn linux_bundles_use_tauri_resource_layout_for_appimage_and_deb() {
    let executable = Path::new("/opt/silicium/usr/bin/silicium-node");
    let candidates = packaged_runtime_candidates(executable, Some(Path::new("/opt/silicium")));

    assert!(candidates.iter().any(|candidate| {
        candidate.ends_with(Path::new("usr/lib/silicium-node/resources/runtime"))
    }));
    assert!(candidates.iter().any(|candidate| {
        candidate.ends_with(Path::new("lib/silicium-node/resources/runtime"))
    }));
}

#[cfg(target_os = "linux")]
#[test]
fn linux_bundles_accept_tauri_product_name_resource_directory() {
    let app_dir = env::temp_dir().join(format!(
        "silicium-product-resource-layout-{}",
        std::process::id()
    ));
    let runtime = app_dir
        .join("usr")
        .join("lib")
        .join("Silicium Node")
        .join("resources")
        .join("runtime")
        .join("Network");
    let _ = fs::remove_dir_all(&app_dir);
    fs::create_dir_all(&runtime).unwrap();
    fs::write(runtime.join("silicium"), b"#!/usr/bin/env python3\n").unwrap();

    let candidates = packaged_runtime_candidates(
        Path::new("/opt/silicium/usr/bin/silicium-node"),
        Some(&app_dir),
    );

    assert!(candidates.iter().any(|candidate| {
        candidate.ends_with(Path::new("usr/lib/Silicium Node/resources/runtime"))
    }));
    assert!(candidates
        .iter()
        .any(|candidate| validate_repo_root(candidate).is_ok()));
    fs::remove_dir_all(app_dir).unwrap();
}

#[cfg(target_os = "linux")]
#[test]
fn linux_appimage_wrapper_ancestors_find_product_runtime_without_appdir() {
    let app_dir = env::temp_dir().join(format!(
        "silicium-appimage-wrapper-layout-{}",
        std::process::id()
    ));
    let runtime = app_dir
        .join("usr")
        .join("lib")
        .join("Silicium Node")
        .join("resources")
        .join("runtime")
        .join("Network");
    let _ = fs::remove_dir_all(&app_dir);
    fs::create_dir_all(&runtime).unwrap();
    fs::write(runtime.join("silicium"), b"#!/usr/bin/env python3\n").unwrap();

    let candidates = packaged_runtime_candidates(&app_dir.join("AppRun.wrapped"), None);

    assert!(candidates
        .iter()
        .any(|candidate| validate_repo_root(candidate).is_ok()));
    fs::remove_dir_all(app_dir).unwrap();
}

#[test]
fn packaged_runtime_requires_the_network_launcher() {
    let directory = env::temp_dir().join(format!(
        "silicium-runtime-validation-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&directory);
    fs::create_dir_all(directory.join("Network")).unwrap();
    assert_eq!(
        validate_repo_root(&directory).unwrap_err(),
        "network_runtime_not_found"
    );
    fs::write(
        directory.join("Network").join("silicium"),
        b"#!/usr/bin/env python3\n",
    )
    .unwrap();
    assert!(validate_repo_root(&directory).is_ok());
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn release_versions_keep_dev_and_prod_ordering() {
    assert!(version_is_newer("0.2.9-dev.2", "0.2.9-dev.1"));
    assert!(version_is_newer("0.2.9", "0.2.9-dev.9"));
    assert!(!version_is_newer("0.2.9-dev.1", "0.2.9"));
    assert!(!version_is_newer("0.2.9-dev.1", "0.2.9-dev.1"));
}

#[test]
fn same_version_with_a_different_published_build_requires_update() {
    assert!(release_requires_update(
        "0.2.9-dev.11",
        "new-build",
        "0.2.9-dev.11",
        "old-build"
    ));
    assert!(!release_requires_update(
        "0.2.9-dev.11",
        "same-build",
        "0.2.9-dev.11",
        "same-build"
    ));
    assert!(!release_requires_update(
        "0.2.9-dev.11",
        "",
        "0.2.9-dev.11",
        "old-build"
    ));
    assert!(!release_requires_update(
        "0.2.9-dev.10",
        "other-build",
        "0.2.9-dev.11",
        "current-build"
    ));
}

#[test]
fn update_install_lease_allows_only_one_installer_for_a_content_id() {
    let directory = env::temp_dir().join(format!("silicium-update-lease-{}", std::process::id()));
    let _ = fs::remove_dir_all(&directory);
    fs::create_dir_all(&directory).unwrap();
    let path = directory.join("install.lock");
    assert!(acquire_install_lock_at(&path, "content-a", Duration::from_secs(60)).unwrap());
    assert!(!acquire_install_lock_at(&path, "content-a", Duration::from_secs(60)).unwrap());
    assert!(!acquire_install_lock_at(&path, "content-b", Duration::from_secs(60)).unwrap());
    fs::remove_file(&path).unwrap();
    assert!(acquire_install_lock_at(&path, "content-b", Duration::from_secs(60)).unwrap());
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn managed_runtime_cleanup_removes_obsolete_build_assets() {
    let directory =
        env::temp_dir().join(format!("silicium-runtime-cleanup-{}", std::process::id()));
    let _ = fs::remove_dir_all(&directory);
    let legacy = directory.join("tools").join("openssl").join("bin");
    let python_crypto = directory
        .join("tools")
        .join("python")
        .join("Lib")
        .join("site-packages")
        .join("cryptography");
    let obsolete_p2p_target = directory
        .join("Network")
        .join("networked")
        .join("p2p_node")
        .join("target")
        .join("release");
    let networked_runtime = directory
        .join("Network")
        .join("networked")
        .join("networked_runtime.py");
    fs::create_dir_all(&legacy).unwrap();
    fs::create_dir_all(&python_crypto).unwrap();
    fs::create_dir_all(&obsolete_p2p_target).unwrap();
    fs::write(legacy.join("openssl.exe"), b"legacy").unwrap();
    fs::write(python_crypto.join("_rust.pyd"), b"keep").unwrap();
    fs::write(obsolete_p2p_target.join("p2p_node.exe"), b"remove").unwrap();
    fs::write(&networked_runtime, b"keep").unwrap();

    remove_legacy_runtime_assets(&directory).unwrap();

    assert!(!directory.join("tools").join("openssl").exists());
    assert!(python_crypto.join("_rust.pyd").exists());
    assert!(!directory
        .join("Network")
        .join("networked")
        .join("p2p_node")
        .exists());
    assert!(networked_runtime.exists());
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn missing_claim_health_is_stale_after_the_supervisor_grace_period() {
    let directory = env::temp_dir().join(format!("silicium-claim-health-{}", std::process::id()));
    let _ = fs::remove_dir_all(&directory);
    assert!(!claim_poll_is_fresh(&directory, Duration::from_secs(60)));

    let health_path = claim_poll_health_path(&directory);
    fs::create_dir_all(health_path.parent().unwrap()).unwrap();
    fs::write(&health_path, b"{}").unwrap();
    assert!(claim_poll_is_fresh(&directory, Duration::from_secs(60)));
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn readiness_requires_the_integrated_network_health_response() {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = [0_u8; 512];
        let _ = stream.read(&mut request);
        stream
            .write_all(
                b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"ok\":true,\"service\":\"network_node\"}",
            )
            .unwrap();
    });

    assert!(local_network_node_ready(port));
    server.join().unwrap();

    let unexpected_listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let unexpected_port = unexpected_listener.local_addr().unwrap().port();
    let unexpected_server = thread::spawn(move || {
        let (mut stream, _) = unexpected_listener.accept().unwrap();
        let mut request = [0_u8; 512];
        let _ = stream.read(&mut request);
        stream
            .write_all(
                b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"ok\":true,\"service\":\"p2p_node\"}",
            )
            .unwrap();
    });
    assert!(!local_network_node_ready(unexpected_port));
    unexpected_server.join().unwrap();
}

#[test]
fn legacy_runtime_cleanup_runs_for_gui_and_supervisor_startup() {
    let source = crate_source();
    assert!(source.contains("remove_legacy_runtime_assets(&managed_runtime_root())"));
    assert!(source.contains("remove_legacy_runtime_assets(&repo_root)"));
}

#[test]
fn managed_runtime_copy_never_restores_the_legacy_openssl_cli() {
    let directory = env::temp_dir().join(format!("silicium-runtime-copy-{}", std::process::id()));
    let _ = fs::remove_dir_all(&directory);
    let source = directory.join("source");
    let target = directory.join("target");
    fs::create_dir_all(source.join("tools").join("openssl").join("bin")).unwrap();
    fs::create_dir_all(source.join("Network")).unwrap();
    fs::write(
        source
            .join("tools")
            .join("openssl")
            .join("bin")
            .join("openssl.exe"),
        b"legacy",
    )
    .unwrap();
    fs::write(source.join("Network").join("silicium"), b"keep").unwrap();

    copy_dir_all(&source, &target).unwrap();

    assert!(!target.join("tools").join("openssl").exists());
    assert!(target.join("Network").join("silicium").exists());
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn raytracer_env_resolves_relative_paths_from_runtime_root() {
    let directory = env::temp_dir().join(format!("silicium-raytracer-env-{}", std::process::id()));
    let _ = fs::remove_dir_all(&directory);
    let env_file = directory
        .join(".silicium")
        .join("env")
        .join("raytracer.env");
    fs::create_dir_all(env_file.parent().unwrap()).unwrap();
    fs::write(
        &env_file,
        "SILICIUM_RAYTRACER_BIN=Network/bin/raytracer/silicium-raytracer\nSILICIUM_RAYTRACER_ASSETS_DIR=Network/bin/raytracer\n",
    )
    .unwrap();

    let mut command = Command::new("silicium-test");
    apply_raytracer_env(&mut command, &directory);

    let value_for = |name: &str| {
        command
            .get_envs()
            .find(|(key, _)| *key == name)
            .and_then(|(_, value)| value)
            .map(PathBuf::from)
    };
    assert_eq!(
        value_for("SILICIUM_RAYTRACER_BIN"),
        Some(
            directory
                .join("Network")
                .join("bin")
                .join("raytracer")
                .join("silicium-raytracer")
        )
    );
    assert_eq!(
        value_for("SILICIUM_RAYTRACER_ASSETS_DIR"),
        Some(directory.join("Network").join("bin").join("raytracer"))
    );
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn automatic_update_script_restarts_the_notification_shell() {
    let source = crate_source();
    assert!(source.contains("[string]$RepoRoot"));
    assert!(source.contains("service-config.env"));
    assert!(source.contains("notification_shell_restarted"));
    assert!(source.contains("-ArgumentList '--background'"));
    assert!(source.contains("installer_launch_retry"));
    assert!(source.contains("acquire_update_install_lock"));
    assert!(source.contains("[string]$InstallLockPath"));
    assert!(source.contains("[string]$FailurePath"));
    assert!(source.contains("update-install-failure.json"));
    assert!(source.contains("update_install_blocked"));
    assert!(source.contains("failedAtUtc"));
    assert!(source.contains("Remove-Item -LiteralPath $InstallLockPath"));
    assert!(source.contains("supervisor_recovered_after_update_failure"));
    assert!(source.contains("stale_node_runtime_stopped"));
    assert!(source.contains("Get-CimInstance Win32_Process"));
    assert!(source.contains("IndexOf('silicium node start'"));
    assert!(source.contains("kill_managed_node_processes(&repo_root)"));
}

#[test]
fn windows_login_starts_the_notification_shell() {
    let command = windows_autostart_command(Path::new(r"C:\Program Files\Silicium Node.exe"));
    assert_eq!(
        command,
        r#""C:\Program Files\Silicium Node.exe" --background"#
    );
    assert!(!command.contains("--supervisor"));
}

#[test]
fn update_release_requires_the_pinned_ed25519_signature() {
    let release = UpdateRelease {
        version: "0.2.9-dev.8".to_string(),
        build: "test-build".to_string(),
        channel: "dev".to_string(),
        platform: String::new(),
        url: "https://vps-910c1dbc.vps.ovh.net/downloads/silicium-node-windows-dev.exe".to_string(),
        sha256: "a".repeat(64),
        content_id: "a".repeat(64),
        signature: "sVOJv9gTgrP9GS5dcuvgvX/Ff6hsnlkguSgvnvIvZHVqD6YwP89jZzYPjuBk4eBaBGE9SkPE+ShmSnZw42XNCg==".to_string(),
        signing_key_id: UPDATE_SIGNING_KEY_ID.to_string(),
        size_bytes: 1234,
        auto_install: true,
        check_interval_seconds: 30,
    };
    assert!(validate_update_release(&release).is_ok());
    let mut tampered = release.clone();
    tampered.size_bytes += 1;
    assert_eq!(
        validate_update_release(&tampered).unwrap_err(),
        "update_signature_untrusted"
    );
}

#[test]
fn update_release_platform_prevents_cross_os_installers() {
    assert!(update_platform_matches(&update_platform()));
    assert!(!update_platform_matches("unsupported-test-platform"));
    assert_eq!(update_platform_matches(""), cfg!(target_os = "windows"));
}

#[test]
fn failed_update_is_blocked_only_for_the_same_artifact() {
    let release = UpdateRelease {
        version: "0.2.9".to_string(),
        build: "build-a".to_string(),
        channel: "prod".to_string(),
        platform: String::new(),
        url: String::new(),
        sha256: String::new(),
        content_id: "content-a".to_string(),
        signature: String::new(),
        signing_key_id: String::new(),
        size_bytes: 0,
        auto_install: true,
        check_interval_seconds: 0,
    };
    let failure = UpdateInstallFailure {
        content_id: "content-a".to_string(),
        version: release.version.clone(),
        build: release.build.clone(),
        error: "installer_exit_1".to_string(),
        failed_at_utc: current_utc(),
    };
    assert!(update_install_failure_matches(&failure, &release));
    let mut new_release = release.clone();
    new_release.content_id = "content-b".to_string();
    assert!(!update_install_failure_matches(&failure, &new_release));
}

#[test]
fn update_artifact_hash_is_portable() {
    let path = env::temp_dir().join(format!(
        "silicium-update-hash-{}-{}.bin",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::write(&path, b"abc").unwrap();
    assert_eq!(
        sha256_file(&path).unwrap(),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
    fs::remove_file(path).unwrap();
}

#[test]
fn machine_activity_reads_work_and_last_response() {
    let directory =
        env::temp_dir().join(format!("silicium-machine-activity-{}", std::process::id()));
    let _ = fs::remove_dir_all(&directory);
    fs::create_dir_all(&directory).unwrap();
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs();
    fs::write(
        directory.join("mesh.discovery.json"),
        format!(
            r#"{{"peers":[{{"node_id":"worker-a","roles":["compute"],"app_version":"0.2.9-dev.1","release_channel":"dev","release_build":"test","last_seen_unix":{now},"last_claim_poll_unix":{now},"last_claim_poll_utc":"2026-07-13T18:00:00Z","last_claim_error":"","updated_utc":"2026-07-13T18:00:00Z","activity":{{"status":"working","active_tasks":[{{"item_id":"render:1","role":"compute","activity":"fragment","workload":"raytracer-fragment","fragment_index":3,"fragment_count":16,"x_start":0,"x_end":100,"y_start":0,"y_end":100}}],"last_response":{{"item_id":"verify:2","ok":true,"timestamp_utc":"2026-07-13T17:59:00Z"}}}},"task_queue":[{{"item_id":"verify:3","kind":"task","role":"verify","activity":"verify","workload":"verification/rendering/raytracer-fragment","fragment_index":3,"fragment_count":16,"source_task_id":"render:1","source_node_id":"worker-b","status":"queued","priority":"high","assigned_peer_id":"","origin_node_id":"orchestrator-1","x_start":0,"x_end":100,"y_start":0,"y_end":100}}]}}]}}"#
        ),
    )
    .unwrap();

    let machines = collect_machine_activity(&directory);
    assert_eq!(machines.len(), 1);
    assert!(machines[0].online);
    assert!(machines[0].scheduler_active);
    assert_eq!(machines[0].status, "working");
    assert_eq!(machines[0].app_version, "0.2.9-dev.1");
    assert_eq!(machines[0].release_channel, "dev");
    assert_eq!(machines[0].active_tasks[0].fragment_index, "3");
    assert_eq!(machines[0].active_tasks[0].fragment_count, "16");
    assert_eq!(machines[0].active_tasks[0].bounds, "x 0..100, y 0..100");
    assert_eq!(machines[0].task_queue[0].role, "verify");
    assert_eq!(machines[0].task_queue[0].source_node_id, "worker-b");
    assert_eq!(machines[0].last_response_ok, Some(true));
    let _ = fs::remove_dir_all(&directory);
}

#[test]
fn runtime_telemetry_parser_preserves_resource_metrics() {
    let payload: Value = serde_json::json!({
        "sampled_unix": 1_784_000_000_u64,
        "node_uptime_seconds": 42.5,
        "process_cpu_percent": 37.25,
        "process_rss_bytes": 134_217_728_u64,
        "system_cpu_percent": 68.5,
        "system_memory_total_bytes": 17_179_869_184_u64,
        "system_memory_used_bytes": 8_589_934_592_u64,
        "system_memory_percent": 50.0,
        "logical_cpu_count": 16_u64,
        "python_thread_count": 7_u64,
        "storage_used_percent": 61.2
    });
    let telemetry = parse_runtime_telemetry(Some(&payload));
    assert_eq!(telemetry.sampled_unix, 1_784_000_000);
    assert_eq!(telemetry.process_rss_bytes, 134_217_728);
    assert_eq!(telemetry.logical_cpu_count, 16);
    assert_eq!(telemetry.python_thread_count, 7);
    assert!((telemetry.process_cpu_percent - 37.25).abs() < f64::EPSILON);
    assert!((telemetry.system_memory_percent - 50.0).abs() < f64::EPSILON);
}
