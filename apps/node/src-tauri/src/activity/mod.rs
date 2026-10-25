//! Activity shown in the UI: node log tail and the event history of the
//! node (`node.events.ndjson`, written by the Rust node).
//! The per-machine activity view is built in [`machine`].

mod machine;

pub(crate) use machine::*;

use crate::*;

pub(crate) fn read_node_log_tail(repo_root: &Path) -> Option<String> {
    let mut parts = Vec::new();
    for (label, name) in [
        ("supervisor stderr", "silicium-supervisor.err.log"),
        ("supervisor stdout", "silicium-supervisor.out.log"),
        ("stderr", "silicium-node.err.log"),
        ("stdout", "silicium-node.out.log"),
    ] {
        let path = node_app_log_path(repo_root, name);
        let Ok(mut file) = fs::File::open(path) else {
            continue;
        };
        let mut content = String::new();
        if file.read_to_string(&mut content).is_err() {
            continue;
        }
        let tail = content
            .lines()
            .rev()
            .take(30)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect::<Vec<_>>()
            .join("\n");
        if !tail.trim().is_empty() {
            parts.push(format!("{label}:\n{tail}"));
        }
    }
    let network_export = runtime_export_dir(repo_root);
    let claim_health = network_export.join("claim-poll.health.json");
    if let Ok(content) = fs::read_to_string(claim_health) {
        if !content.trim().is_empty() {
            parts.push(format!("scheduler claim health:\n{}", content.trim()));
        }
    }
    let claim_events = network_export.join("node.events.ndjson");
    if let Ok(content) = fs::read_to_string(claim_events) {
        let tail = content
            .lines()
            .rev()
            .filter(|line| line.contains("\"kind\":\"claim_"))
            .take(12)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect::<Vec<_>>()
            .join("\n");
        if !tail.trim().is_empty() {
            parts.push(format!("scheduler claim events:\n{tail}"));
        }
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join("\n\n"))
    }
}

pub(crate) fn collect_event_history(path: &Path, history: &mut Vec<HistoryItem>) {
    let Ok(raw) = fs::read_to_string(path) else {
        return;
    };
    for line in raw.lines().rev().take(500) {
        let Ok(value) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        let kind = value
            .get("kind")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim();
        let item_id = value
            .get("item_id")
            .and_then(Value::as_str)
            .unwrap_or("task")
            .trim();
        let timestamp = value
            .get("timestamp_utc")
            .and_then(Value::as_str)
            .and_then(parse_utc_timestamp)
            .unwrap_or(0);
        let duration_ms = value
            .get("duration_ms")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let ok = value.get("ok").and_then(Value::as_bool).unwrap_or(true);
        let verification = value.get("role").and_then(Value::as_str) == Some("verify");
        let name = match kind {
            "task" if verification && ok => format!("verify.{item_id}"),
            "task_received" | "pull_claim" => format!("task.received.{item_id}"),
            "task_started" => format!("task.started.{item_id}"),
            "fragment_fetched" => format!("fragment.fetched.{item_id}"),
            "verification_input_fetched" => format!("verification.fetched.{item_id}"),
            "task_input_fetched" => format!("task.input_fetched.{item_id}"),
            "task" | "request" if ok => format!("result.{item_id}"),
            "task" | "request" => format!("failed.{item_id}"),
            "result_return" if ok => format!("result.sent.{item_id}"),
            "result_return" => format!("result.return_failed.{item_id}"),
            _ => continue,
        };
        history.push(HistoryItem {
            name,
            modified_at: timestamp,
            size_bytes: duration_ms,
            kind: kind.to_string(),
            item_id: item_id.to_string(),
            role: value
                .get("role")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            activity: value
                .get("activity")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            fragment_index: json_value_text(value.get("fragment_index")),
            ok: value.get("ok").and_then(Value::as_bool),
            peer_id: value
                .get("source_peer")
                .or_else(|| value.get("source_node"))
                .or_else(|| value.get("target_node"))
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
        });
    }
}

pub(crate) fn parse_utc_timestamp(value: &str) -> Option<u64> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|datetime| datetime.with_timezone(&Utc).timestamp())
        .filter(|timestamp| *timestamp >= 0)
        .map(|timestamp| timestamp as u64)
}

pub(crate) fn directory_size(path: &Path) -> u64 {
    let Ok(entries) = fs::read_dir(path) else {
        return 0;
    };
    entries
        .flatten()
        .map(|entry| {
            let Ok(metadata) = entry.metadata() else {
                return 0;
            };
            if metadata.is_dir() {
                directory_size(&entry.path())
            } else {
                metadata.len()
            }
        })
        .sum()
}
