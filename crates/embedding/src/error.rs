//! Error type of the crate. Every variant carries a message that can be
//! shown to an operator; [`Error::user_message`] gives the French sentence
//! shown to the person who submitted the documents, when there is one.

use std::fmt;

/// Result of this crate.
pub type Result<T> = std::result::Result<T, Error>;

/// What can go wrong while preparing, encoding or searching.
#[derive(Debug)]
pub enum Error {
    /// A file could not be read or written.
    Io(std::io::Error),
    /// The submitted documents are not usable (no text, unsupported format,
    /// too large...). The message is meant for the end user.
    Input(String),
    /// A data file (corpus, vector block, index) is malformed.
    Format(String),
    /// The model files are missing, corrupted or could not be downloaded.
    Model(String),
    /// The model failed while computing.
    Compute(String),
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
            Error::Model(message) => write!(f, "model: {message}"),
            Error::Compute(message) => write!(f, "compute: {message}"),
        }
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(err: std::io::Error) -> Self {
        Error::Io(err)
    }
}

impl From<candle_core::Error> for Error {
    fn from(err: candle_core::Error) -> Self {
        Error::Compute(err.to_string())
    }
}
