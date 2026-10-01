//! JSON Lines persistence of the task book: one serialized event per line,
//! appended in acceptance order and replayed through [`TaskBook::append`] on
//! load.

use std::{
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::Path,
};

use super::{TaskBook, TaskBookError, TaskEvent};

impl TaskBook {
    /// Validates `event` and, if accepted, appends it to the file at `path`
    /// before updating `self`; returns the event hash.
    ///
    /// Validation runs on a clone so that `self` is left untouched when the
    /// event is refused or the write fails. An event already present is not
    /// written again.
    pub fn append_persisted(
        &mut self,
        path: impl AsRef<Path>,
        event: TaskEvent,
    ) -> Result<String, TaskBookError> {
        let event_hash = event.event_hash();
        if let Some(existing) = self.events.get(&event_hash)
            && existing == &event
        {
            return Ok(event_hash);
        }
        let mut next = self.clone();
        let event_hash = next.append(event.clone())?;
        append_event_line(path.as_ref(), &event)?;
        *self = next;
        Ok(event_hash)
    }

    /// Rebuilds a task book from the file at `path` (empty book if the file
    /// does not exist). Blank lines are skipped; any invalid event aborts the
    /// load.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, TaskBookError> {
        let path = path.as_ref();
        if !path.exists() {
            return Ok(Self::default());
        }
        let file = fs::File::open(path).map_err(|err| TaskBookError::Io(err.to_string()))?;
        let mut book = Self::default();
        for line in BufReader::new(file).lines() {
            let line = line.map_err(|err| TaskBookError::Io(err.to_string()))?;
            if line.trim().is_empty() {
                continue;
            }
            let event: TaskEvent = serde_json::from_str(&line)
                .map_err(|err| TaskBookError::Serialization(err.to_string()))?;
            book.append(event)?;
        }
        Ok(book)
    }
}

/// Creates the parent directory if needed and appends `event` as one JSON
/// line to `path`.
fn append_event_line(path: &Path, event: &TaskEvent) -> Result<(), TaskBookError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| TaskBookError::Io(err.to_string()))?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|err| TaskBookError::Io(err.to_string()))?;
    serde_json::to_writer(&mut file, event)
        .map_err(|err| TaskBookError::Serialization(err.to_string()))?;
    file.write_all(b"\n")
        .map_err(|err| TaskBookError::Io(err.to_string()))?;
    Ok(())
}
