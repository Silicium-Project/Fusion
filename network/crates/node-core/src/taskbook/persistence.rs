//! JSON Lines persistence of the task book: one serialized event per line,
//! written in acceptance order and replayed through [`TaskBook::append`] on
//! load. A torn last line (crash during a write) is skipped instead of
//! preventing the node from starting.

use std::{
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::Path,
};

use super::{Received, TaskBook, TaskBookError, TaskEvent};

/// What [`TaskBook::load_with_report`] had to skip.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct LoadReport {
    /// The last line could not be read back (torn write) and was ignored.
    pub skipped_last_line: bool,
}

impl TaskBook {
    /// [`TaskBook::receive`], writing every event added to the book to the
    /// file at `path` before it is inserted (events waiting for a
    /// predecessor are not written: they are fetched again if lost).
    pub fn receive_persisted(
        &mut self,
        path: impl AsRef<Path>,
        event: TaskEvent,
    ) -> Result<Received, TaskBookError> {
        let path = path.as_ref();
        let mut accepted = Vec::new();
        let pending = self.receive_with(event, |event, hash| {
            append_event_line(path, event)?;
            accepted.push(hash.to_string());
            Ok(())
        })?;
        Ok(Received { accepted, pending })
    }

    /// Appends a local event (next in its author's chain) to the book and to
    /// the file at `path`; returns the event hash.
    pub fn append_persisted(
        &mut self,
        path: impl AsRef<Path>,
        event: TaskEvent,
    ) -> Result<String, TaskBookError> {
        let hash = event.event_hash();
        let received = self.receive_persisted(path, event)?;
        if received.pending {
            return Err(TaskBookError::InvalidInitialSequence);
        }
        Ok(hash)
    }

    /// Rebuilds a task book from the file at `path` (empty book if the file
    /// does not exist).
    pub fn load(path: impl AsRef<Path>) -> Result<Self, TaskBookError> {
        Self::load_with_report(path).map(|(book, _)| book)
    }

    /// Like [`TaskBook::load`], also saying whether a torn last line was
    /// skipped. Blank lines are ignored; an invalid line anywhere else aborts.
    pub fn load_with_report(path: impl AsRef<Path>) -> Result<(Self, LoadReport), TaskBookError> {
        let path = path.as_ref();
        let mut book = Self::default();
        let mut report = LoadReport::default();
        if !path.exists() {
            return Ok((book, report));
        }
        let lines = read_lines(path)?;
        let last = lines.len().saturating_sub(1);
        for (index, line) in lines.iter().enumerate() {
            let loaded = serde_json::from_str::<TaskEvent>(line)
                .map_err(|err| TaskBookError::Serialization(err.to_string()))
                .and_then(|event| book.append(event));
            match loaded {
                Ok(_) => {}
                Err(_) if index == last => report.skipped_last_line = true,
                Err(error) => return Err(error),
            }
        }
        Ok((book, report))
    }
}

/// Non-blank lines of the file at `path`.
fn read_lines(path: &Path) -> Result<Vec<String>, TaskBookError> {
    let file = fs::File::open(path).map_err(|err| TaskBookError::Io(err.to_string()))?;
    let mut lines = Vec::new();
    for line in BufReader::new(file).lines() {
        let line = line.map_err(|err| TaskBookError::Io(err.to_string()))?;
        if !line.trim().is_empty() {
            lines.push(line);
        }
    }
    Ok(lines)
}

/// Creates the parent directory if needed and appends `event` as one JSON
/// line to `path`.
fn append_event_line(path: &Path, event: &TaskEvent) -> Result<(), TaskBookError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| TaskBookError::Io(err.to_string()))?;
    }
    let mut line =
        serde_json::to_vec(event).map_err(|err| TaskBookError::Serialization(err.to_string()))?;
    line.push(b'\n');
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|err| TaskBookError::Io(err.to_string()))?;
    // One write call per line keeps a crash from interleaving two events.
    file.write_all(&line)
        .map_err(|err| TaskBookError::Io(err.to_string()))
}
