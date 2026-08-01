use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RuntimeKind {
    Wasm,
    Oci,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeLimits {
    pub memory_limit_mib: u32,
    pub cpu_timeout_ms: u64,
    pub gpu_enabled: bool,
}

impl RuntimeLimits {
    pub fn wasm_default() -> Self {
        Self {
            memory_limit_mib: 128,
            cpu_timeout_ms: 5_000,
            gpu_enabled: false,
        }
    }

    pub fn oci_default() -> Self {
        Self {
            memory_limit_mib: 1_024,
            cpu_timeout_ms: 60_000,
            gpu_enabled: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeEnvelope {
    pub kind: RuntimeKind,
    pub limits: RuntimeLimits,
    pub command: Vec<String>,
}

impl RuntimeEnvelope {
    pub fn wasm(command: impl Into<Vec<String>>) -> Self {
        Self {
            kind: RuntimeKind::Wasm,
            limits: RuntimeLimits::wasm_default(),
            command: command.into(),
        }
    }

    pub fn oci(command: impl Into<Vec<String>>) -> Self {
        Self {
            kind: RuntimeKind::Oci,
            limits: RuntimeLimits::oci_default(),
            command: command.into(),
        }
    }
}
