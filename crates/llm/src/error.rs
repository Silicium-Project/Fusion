//! Error type of the crate. [`Error::Input`] carries a French sentence for
//! the person who submitted the job; the other variants are for operators.

use std::fmt;

/// Result of this crate.
pub type Result<T> = std::result::Result<T, Error>;

/// What can go wrong while preparing, computing or assembling a batch.
#[derive(Debug)]
pub enum Error {
    /// A file could not be read or written.
    Io(std::io::Error),
    /// The submitted request is not usable. The message is for the end user.
    Input(String),
    /// A data file (batch, answers) is malformed.
    Format(String),
    /// Ollama is unreachable, refused a request or answered nonsense.
    Ollama(String),
}

impl Error {
    /// French message for the end user, when the error comes from what they
    /// submitted.
    pub fn user_message(&self) -> Option<&str> {
        match self {
            Error::Input(message) => Some(message),
            _ => None,
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Io(err) => write!(f, "io: {err}"),
            Error::Input(message) => write!(f, "input: {message}"),
            Error::Format(message) => write!(f, "format: {message}"),
            Error::Ollama(message) => write!(f, "ollama: {message}"),
        }
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(err: std::io::Error) -> Self {
        Error::Io(err)
    }
}

impl From<serde_json::Error> for Error {
    fn from(err: serde_json::Error) -> Self {
        Error::Format(err.to_string())
    }
}
