//! Submitted documents to corpus, on the publisher.
//!
//! The files come from users of the site: a malformed or hostile PDF can
//! make a parser loop, exhaust memory or panic. The node therefore parses
//! them in a child process (this same executable, run as
//! `p2p_node embedding-prepare <input> <output>`), killed after
//! `SILICIUM_EMBEDDING_PREPARE_TIMEOUT_S` (default 300 s): a bad file costs
//! one job, never the node. Tests, and nodes started with
//! `SILICIUM_EMBEDDING_PREPARE_IN_PROCESS=1`, parse in process.
//!
//! The child gets at most `SILICIUM_EMBEDDING_PREPARE_MEMORY_MB` of memory
//! (default 2048, Unix) and is the first process the Linux out-of-memory
//! killer picks; at most `SILICIUM_EMBEDDING_PREPARE_PARALLEL` (default 2)
//! run at once.
//!
//! The child exits with 0 (corpus written), [`EXIT_INPUT`] (the documents
//! are not usable; the message for the user is in `<output>.error`) or any
//! other code (internal failure).

use silicium_embedding::{
    corpus,
    documents::{self, Limits},
    passages::Chunker,
};
use std::{
    path::{Path, PathBuf},
    process::{Command, ExitStatus, Stdio},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

/// First argument that runs the child (see the module documentation).
pub(crate) const SUBCOMMAND: &str = "embedding-prepare";
/// Exit code of a child that refused the documents.
const EXIT_INPUT: i32 = 2;
/// Message when the text of the documents is over what one job carries.
const TOO_MUCH_TEXT: &str =
    "Tes documents contiennent trop de texte pour un seul envoi. Envoie-les en plusieurs fois.";
/// Message when the documents could not be processed for another reason.
const GENERIC_FAILURE: &str =
    "Les documents n'ont pas pu être préparés. Réessaie, ou envoie-les en plusieurs fois.";

/// The corpus of the submitted file `submitted`, or a message for the user.
pub(crate) fn prepare(submitted: &Path) -> Result<Vec<u8>, String> {
    if in_process() {
        return build_corpus(submitted);
    }
    let _slot = PreparationSlot::take();
    let output = temporary_output();
    let result = run_child(submitted, &output);
    let _ = std::fs::remove_file(&output);
    let _ = std::fs::remove_file(error_path(&output));
    result
}

/// Entry point of the child process: `args` are the arguments after
/// [`SUBCOMMAND`]. Returns the exit code.
pub(crate) fn run_subcommand(args: &[String]) -> i32 {
    let [input, output] = args else {
        eprintln!("usage: p2p_node {SUBCOMMAND} <input> <output>");
        return 1;
    };
    let output = PathBuf::from(output);
    match build_corpus(Path::new(input)) {
        Ok(bytes) => match std::fs::write(&output, bytes) {
            Ok(()) => 0,
            Err(err) => {
                eprintln!("corpus not written: {err}");
                1
            }
        },
        Err(message) => {
            let _ = std::fs::write(error_path(&output), message);
            EXIT_INPUT
        }
    }
}

/// Reads the documents and builds their corpus, in this process.
pub(crate) fn build_corpus(submitted: &Path) -> Result<Vec<u8>, String> {
    let extraction = documents::extract(submitted, &Limits::default()).map_err(user_message)?;
    let corpus = corpus::build(&extraction, &Chunker::default()).map_err(user_message)?;
    // The corpus is shared with the workers as one content.
    if corpus.len() > crate::content::MAX_CONTENT_BYTES {
        return Err(TOO_MUCH_TEXT.to_string());
    }
    Ok(corpus)
}

fn user_message(err: silicium_embedding::Error) -> String {
    match err.user_message() {
        Some(message) => message.to_string(),
        None => {
            println!(" Documents not prepared: {err}");
            GENERIC_FAILURE.to_string()
        }
    }
}

fn run_child(submitted: &Path, output: &Path) -> Result<Vec<u8>, String> {
    let executable = std::env::current_exe().map_err(|_| GENERIC_FAILURE.to_string())?;
    let mut command = Command::new(executable);
    command
        .arg(SUBCOMMAND)
        .arg(submitted)
        .arg(output)
        .stdin(Stdio::null());
    limit_child(&mut command);
    let child = command.spawn();
    let mut child = child.map_err(|err| {
        println!(" Could not start the document preparation: {err}");
        GENERIC_FAILURE.to_string()
    })?;
    let status = wait_with_timeout(&mut child, timeout());
    match status {
        Some(status) if status.success() => {
            std::fs::read(output).map_err(|_| GENERIC_FAILURE.to_string())
        }
        Some(status) if status.code() == Some(EXIT_INPUT) => {
            Err(std::fs::read_to_string(error_path(output))
                .unwrap_or_else(|_| GENERIC_FAILURE.to_string()))
        }
        Some(status) => {
            println!(" Document preparation failed: {status}");
            Err(GENERIC_FAILURE.to_string())
        }
        None => {
            println!(
                " Document preparation killed after {} s",
                timeout().as_secs()
            );
            Err(
                "La lecture des documents a pris trop de temps. Envoie-les en plusieurs fois."
                    .to_string(),
            )
        }
    }
}

/// Waits for the child, killing it at `timeout`; `None` when killed.
fn wait_with_timeout(child: &mut std::process::Child, timeout: Duration) -> Option<ExitStatus> {
    let deadline = Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return Some(status),
            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(50)),
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
        }
    }
}

/// Bounds the memory of the child, and offers it first to the Linux
/// out-of-memory killer (rather than the node holding the model).
#[cfg(unix)]
fn limit_child(command: &mut Command) {
    use std::os::unix::process::CommandExt;
    let bytes =
        env_number("SILICIUM_EMBEDDING_PREPARE_MEMORY_MB", 2048).saturating_mul(1024 * 1024);
    // SAFETY: runs in the forked child before exec; it only calls the
    // async-signal-safe setrlimit, open, write and close.
    unsafe {
        command.pre_exec(move || {
            let limit = libc::rlimit {
                rlim_cur: bytes as libc::rlim_t,
                rlim_max: bytes as libc::rlim_t,
            };
            libc::setrlimit(libc::RLIMIT_AS, &limit);
            let fd = libc::open(c"/proc/self/oom_score_adj".as_ptr(), libc::O_WRONLY);
            if fd >= 0 {
                libc::write(fd, b"1000".as_ptr().cast(), 4);
                libc::close(fd);
            }
            Ok(())
        });
    }
}

#[cfg(not(unix))]
fn limit_child(_command: &mut Command) {}

/// One of the preparations allowed at once, held until dropped.
struct PreparationSlot;

static RUNNING: (std::sync::Mutex<u64>, std::sync::Condvar) =
    (std::sync::Mutex::new(0), std::sync::Condvar::new());

impl PreparationSlot {
    /// Waits for a free slot.
    fn take() -> Self {
        let parallel = env_number("SILICIUM_EMBEDDING_PREPARE_PARALLEL", 2).max(1);
        let (count, freed) = &RUNNING;
        let mut running = count
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        while *running >= parallel {
            running = freed
                .wait(running)
                .unwrap_or_else(|poisoned| poisoned.into_inner());
        }
        *running += 1;
        Self
    }
}

impl Drop for PreparationSlot {
    fn drop(&mut self) {
        let (count, freed) = &RUNNING;
        let mut running = count
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        *running = running.saturating_sub(1);
        freed.notify_one();
    }
}

fn env_number(key: &str, default: u64) -> u64 {
    std::env::var(key)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(default)
}

fn in_process() -> bool {
    cfg!(test)
        || std::env::var("SILICIUM_EMBEDDING_PREPARE_IN_PROCESS")
            .is_ok_and(|value| value.trim() == "1")
}

fn timeout() -> Duration {
    std::env::var("SILICIUM_EMBEDDING_PREPARE_TIMEOUT_S")
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .map(Duration::from_secs)
        .unwrap_or(Duration::from_secs(300))
}

fn temporary_output() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    std::env::temp_dir().join(format!(
        "silicium-corpus-{}-{nanos}.jsonl",
        std::process::id()
    ))
}

fn error_path(output: &Path) -> PathBuf {
    let mut path = output.as_os_str().to_owned();
    path.push(".error");
    PathBuf::from(path)
}
