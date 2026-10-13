//! Resource telemetry of this node, sent in its heartbeat and shown by the
//! desktop app ("Charge de ce PC") and the site: machine CPU and memory,
//! CPU and memory of the Silicium processes, disk of the work directory,
//! uptime.
//!
//! "Silicium processes" are this node and the processes that compute for it
//! on the same machine (`compute_daemon`, `silicium-raytracer`): the render
//! itself runs in the latter. Values are sampled every heartbeat (5 s); CPU
//! usage needs two samples, so the first heartbeat reports 0 %.

use serde_json::{Value, json};
use std::{
    path::{Path, PathBuf},
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use sysinfo::{Disks, ProcessRefreshKind, ProcessesToUpdate, System};

/// Name prefixes of the processes counted as Silicium (`.exe` on Windows).
const SILICIUM_PROCESSES: &[&str] = &["p2p_node", "compute_daemon", "silicium-raytracer"];

/// Sampler kept by the event loop between heartbeats.
pub(crate) struct Telemetry {
    system: System,
    disks: Disks,
    work_dir: PathBuf,
    started: Instant,
    last_sample: Option<Instant>,
    peak_rss_bytes: u64,
}

/// Values of one sample (see [`Telemetry::sample`]).
#[derive(Debug, Clone, Default, PartialEq)]
pub(crate) struct Sample {
    pub(crate) system_cpu_percent: f64,
    pub(crate) logical_cpu_count: usize,
    pub(crate) memory_total_bytes: u64,
    pub(crate) memory_available_bytes: u64,
    /// CPU of the Silicium processes, 100 % = one core.
    pub(crate) process_cpu_one_core_percent: f64,
    pub(crate) process_cpu_seconds: f64,
    pub(crate) process_rss_bytes: u64,
    pub(crate) storage_total_bytes: u64,
    pub(crate) storage_free_bytes: u64,
    pub(crate) load_average: [f64; 3],
    /// Worker threads of the node's async runtime.
    pub(crate) runtime_threads: usize,
}

impl Telemetry {
    /// Sampler for a node whose work directory is `work_dir`.
    pub(crate) fn new(work_dir: PathBuf) -> Self {
        Self {
            system: System::new(),
            disks: Disks::new_with_refreshed_list(),
            work_dir,
            started: Instant::now(),
            last_sample: None,
            peak_rss_bytes: 0,
        }
    }

    /// Refreshes the measures and returns them in the heartbeat format read
    /// by the desktop app (`activity.telemetry`).
    pub(crate) fn sample(&mut self) -> Value {
        let interval_ms = self
            .last_sample
            .map(|at| at.elapsed().as_millis() as u64)
            .unwrap_or(0);
        self.last_sample = Some(Instant::now());
        let sample = self.measure();
        self.peak_rss_bytes = self.peak_rss_bytes.max(sample.process_rss_bytes);
        to_json(
            &sample,
            interval_ms,
            self.started.elapsed().as_secs_f64(),
            self.peak_rss_bytes,
        )
    }

    fn measure(&mut self) -> Sample {
        self.system.refresh_cpu_usage();
        self.system.refresh_memory();
        self.system.refresh_processes_specifics(
            ProcessesToUpdate::All,
            true,
            ProcessRefreshKind::nothing().with_cpu().with_memory(),
        );
        self.disks.refresh(true);
        let mut sample = Sample {
            system_cpu_percent: f64::from(self.system.global_cpu_usage()),
            logical_cpu_count: self.system.cpus().len(),
            memory_total_bytes: self.system.total_memory(),
            memory_available_bytes: self.system.available_memory(),
            ..Sample::default()
        };
        for process in self.system.processes().values() {
            if is_silicium_process(&process.name().to_string_lossy()) {
                sample.process_cpu_one_core_percent += f64::from(process.cpu_usage());
                sample.process_cpu_seconds += process.accumulated_cpu_time() as f64 / 1000.0;
                sample.process_rss_bytes += process.memory();
            }
        }
        if let Some(disk) = disk_of(&self.disks, &self.work_dir) {
            sample.storage_total_bytes = disk.total_space();
            sample.storage_free_bytes = disk.available_space();
        }
        let load = System::load_average();
        sample.load_average = [load.one, load.five, load.fifteen];
        sample.runtime_threads = tokio::runtime::Handle::try_current()
            .map(|runtime| runtime.metrics().num_workers())
            .unwrap_or(0);
        sample
    }
}

/// Longest process name Linux reports (`/proc/<pid>/comm`).
const LINUX_NAME_LEN: usize = 15;

/// True for this node and the processes that compute for it. Linux cuts
/// process names to 15 characters (`silicium-raytra`).
fn is_silicium_process(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    let name = name.strip_suffix(".exe").unwrap_or(&name);
    SILICIUM_PROCESSES.iter().any(|expected| {
        *expected == name || (name.len() == LINUX_NAME_LEN && expected.starts_with(name))
    })
}

/// The disk holding `path`: the one with the longest mount point prefix.
fn disk_of<'a>(disks: &'a Disks, path: &Path) -> Option<&'a sysinfo::Disk> {
    let path = std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    disks
        .list()
        .iter()
        .filter(|disk| path.starts_with(disk.mount_point()))
        .max_by_key(|disk| disk.mount_point().as_os_str().len())
}

fn percent(part: u64, total: u64) -> f64 {
    if total == 0 {
        0.0
    } else {
        part as f64 * 100.0 / total as f64
    }
}

fn round(value: f64) -> f64 {
    (value * 10.0).round() / 10.0
}

/// Heartbeat telemetry, with the field names the desktop app reads.
pub(crate) fn to_json(sample: &Sample, interval_ms: u64, uptime_s: f64, peak_rss: u64) -> Value {
    let cores = sample.logical_cpu_count.max(1) as f64;
    let memory_used = sample
        .memory_total_bytes
        .saturating_sub(sample.memory_available_bytes);
    let storage_used = sample
        .storage_total_bytes
        .saturating_sub(sample.storage_free_bytes);
    json!({
        "sampled_unix": SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0),
        "sample_interval_ms": interval_ms,
        "updated_utc": crate::task::utc_now(),
        "node_uptime_seconds": uptime_s.round(),
        "logical_cpu_count": sample.logical_cpu_count,
        "system_cpu_percent": round(sample.system_cpu_percent),
        "process_cpu_percent": round(sample.process_cpu_one_core_percent / cores),
        "process_cpu_percent_one_core": round(sample.process_cpu_one_core_percent),
        "process_cpu_seconds": round(sample.process_cpu_seconds),
        "process_rss_bytes": sample.process_rss_bytes,
        "process_peak_rss_bytes": peak_rss.max(sample.process_rss_bytes),
        "system_memory_total_bytes": sample.memory_total_bytes,
        "system_memory_available_bytes": sample.memory_available_bytes,
        "system_memory_used_bytes": memory_used,
        "system_memory_percent": round(percent(memory_used, sample.memory_total_bytes)),
        "load_average": sample.load_average,
        "runtime_thread_count": sample.runtime_threads,
        "storage_total_bytes": sample.storage_total_bytes,
        "storage_free_bytes": sample.storage_free_bytes,
        "storage_used_percent": round(percent(storage_used, sample.storage_total_bytes)),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn silicium_processes_are_recognised_on_every_platform() {
        assert!(is_silicium_process("p2p_node"));
        assert!(is_silicium_process("compute_daemon.exe"));
        assert!(is_silicium_process("SILICIUM-RAYTRACER.EXE"));
        assert!(is_silicium_process("silicium-raytra"), "name cut by Linux");
        assert!(!is_silicium_process("chrome.exe"));
    }

    #[test]
    fn the_heartbeat_reports_percentages_of_the_machine() {
        let sample = Sample {
            system_cpu_percent: 37.25,
            logical_cpu_count: 16,
            memory_total_bytes: 16_000,
            memory_available_bytes: 4_000,
            process_cpu_one_core_percent: 200.0,
            process_rss_bytes: 300,
            storage_total_bytes: 1_000,
            storage_free_bytes: 250,
            ..Sample::default()
        };
        let json = to_json(&sample, 5_000, 61.4, 500);
        assert_eq!(json["system_cpu_percent"], 37.3);
        assert_eq!(json["process_cpu_percent_one_core"], 200.0);
        assert_eq!(
            json["process_cpu_percent"], 12.5,
            "two cores out of sixteen"
        );
        assert_eq!(json["system_memory_used_bytes"], 12_000);
        assert_eq!(json["system_memory_percent"], 75.0);
        assert_eq!(json["storage_used_percent"], 75.0);
        assert_eq!(json["process_peak_rss_bytes"], 500);
        assert_eq!(json["node_uptime_seconds"], 61.0);
    }

    #[test]
    fn a_real_sample_measures_this_machine() {
        let mut telemetry = Telemetry::new(std::env::temp_dir());
        telemetry.sample();
        let json = telemetry.sample();
        assert!(json["logical_cpu_count"].as_u64().unwrap() >= 1);
        assert!(json["system_memory_total_bytes"].as_u64().unwrap() > 0);
        assert!(json["storage_total_bytes"].as_u64().unwrap() > 0);
    }
}
