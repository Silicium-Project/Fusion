//! Shared building blocks of a Silicium node (no network I/O here).
//!
//! - [`p2p`]: envelopes exchanged between peers (tasks, DHT records).
//! - [`region`]: rectangle of an image addressed by a task.
//! - [`taskbook`]: Ed25519-signed, per-author chained log of task events.
//! - [`dag`]: dependency graph between tasks.
//! - [`dispatch`], [`beta`], [`affinity`]: node selection and reputation priors.
//! - [`hardware`]: coarse hardware profile of the local machine.
//! - [`runtime`]: execution of a task as WASM (feature `runtime-wasm`) or OCI.
//! - [`sandbox`]: confinement of file paths received from peers or APIs.
//!
//! See `crates/node-core/README.md` for known limitations.

pub mod affinity;
pub mod beta;
pub mod dag;
pub mod dispatch;
pub mod hardware;
pub mod p2p;
pub mod region;
pub mod runtime;
pub mod sandbox;
pub mod taskbook;
