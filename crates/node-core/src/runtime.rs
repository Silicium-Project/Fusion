use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::PathBuf, process::Command};
use thiserror::Error;

#[cfg(feature = "runtime-wasm")]
use wasmtime::{Engine, Linker, Module, Store};
#[cfg(feature = "runtime-wasm")]
use wasmtime_wasi::{
    DirPerms, FilePerms, WasiCtxBuilder,
    p1::{self, WasiP1Ctx},
};

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
    #[serde(default)]
    pub module_path: Option<PathBuf>,
    #[serde(default)]
    pub image: Option<String>,
    #[serde(default)]
    pub working_dir: Option<PathBuf>,
    #[serde(default)]
    pub env: BTreeMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeOutcome {
    pub kind: RuntimeKind,
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
}

#[derive(Debug, Error)]
pub enum RuntimeError {
    #[error("missing wasm module path for runtime execution")]
    MissingWasmModulePath,
    #[error("missing OCI image for runtime execution")]
    MissingOciImage,
    #[error("wasm runtime support is disabled for this build")]
    WasmUnavailable,
    #[error("invalid runtime working directory: {0}")]
    InvalidWorkingDirectory(String),
    #[cfg(feature = "runtime-wasm")]
    #[error("wasmtime error: {0}")]
    Wasmtime(#[from] wasmtime::Error),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("docker exited with status {status}: {stderr}")]
    DockerFailed { status: i32, stderr: String },
}

impl RuntimeEnvelope {
    pub fn wasm(command: impl Into<Vec<String>>) -> Self {
        Self {
            kind: RuntimeKind::Wasm,
            limits: RuntimeLimits::wasm_default(),
            command: command.into(),
            module_path: None,
            image: None,
            working_dir: None,
            env: BTreeMap::new(),
        }
    }

    pub fn oci(command: impl Into<Vec<String>>) -> Self {
        Self {
            kind: RuntimeKind::Oci,
            limits: RuntimeLimits::oci_default(),
            command: command.into(),
            module_path: None,
            image: None,
            working_dir: None,
            env: BTreeMap::new(),
        }
    }

    pub fn with_module_path(mut self, module_path: impl Into<PathBuf>) -> Self {
        self.module_path = Some(module_path.into());
        self
    }

    pub fn with_image(mut self, image: impl Into<String>) -> Self {
        self.image = Some(image.into());
        self
    }

    pub fn with_working_dir(mut self, working_dir: impl Into<PathBuf>) -> Self {
        self.working_dir = Some(working_dir.into());
        self
    }

    pub fn with_env(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.env.insert(key.into(), value.into());
        self
    }

    pub fn execute(&self) -> Result<RuntimeOutcome, RuntimeError> {
        match self.kind {
            RuntimeKind::Wasm => self.execute_wasm(),
            RuntimeKind::Oci => self.execute_oci(),
        }
    }

    #[cfg(feature = "runtime-wasm")]
    fn execute_wasm(&self) -> Result<RuntimeOutcome, RuntimeError> {
        let module_path = self
            .module_path
            .as_ref()
            .ok_or(RuntimeError::MissingWasmModulePath)?;
        let engine = Engine::default();
        let module = Module::from_file(&engine, module_path)?;

        let mut linker: Linker<WasiP1Ctx> = Linker::new(&engine);
        p1::add_to_linker_sync(&mut linker, |ctx| ctx)?;
        let pre = linker.instantiate_pre(&module)?;

        let host_workdir = self.resolve_working_dir()?;
        let mut builder = WasiCtxBuilder::new();
        builder.inherit_stdio();
        builder.initial_cwd(host_workdir.to_string_lossy());
        builder.preopened_dir(&host_workdir, ".", DirPerms::all(), FilePerms::all())?;

        let env_pairs: Vec<(&str, &str)> = self
            .env
            .iter()
            .map(|(key, value)| (key.as_str(), value.as_str()))
            .collect();
        if !env_pairs.is_empty() {
            builder.envs(&env_pairs);
        }
        if !self.command.is_empty() {
            builder.args(&self.command);
        }

        let mut store = Store::new(&engine, builder.build_p1());
        let instance = pre.instantiate(&mut store)?;
        let start = instance.get_typed_func::<(), ()>(&mut store, "_start")?;
        start.call(&mut store, ())?;

        Ok(RuntimeOutcome {
            kind: RuntimeKind::Wasm,
            exit_code: 0,
            stdout: String::new(),
            stderr: String::new(),
        })
    }

    #[cfg(not(feature = "runtime-wasm"))]
    fn execute_wasm(&self) -> Result<RuntimeOutcome, RuntimeError> {
        Err(RuntimeError::WasmUnavailable)
    }

    fn execute_oci(&self) -> Result<RuntimeOutcome, RuntimeError> {
        let image = self.image.as_ref().ok_or(RuntimeError::MissingOciImage)?;
        let host_workdir = self.resolve_working_dir()?;
        let mut command = Command::new("docker");
        command
            .arg("run")
            .arg("--rm")
            .arg("--network")
            .arg("none")
            .arg("--memory")
            .arg(format!("{}m", self.limits.memory_limit_mib))
            .arg("-v")
            .arg(format!("{}:/work", host_workdir.to_string_lossy()))
            .arg("-w")
            .arg("/work");

        if self.limits.gpu_enabled {
            command.arg("--gpus").arg("all");
        }

        for (key, value) in &self.env {
            command.arg("-e").arg(format!("{key}={value}"));
        }

        command.arg(image);
        command.args(&self.command);

        let output = command.output()?;
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();

        if !output.status.success() {
            return Err(RuntimeError::DockerFailed {
                status: output.status.code().unwrap_or(-1),
                stderr,
            });
        }

        Ok(RuntimeOutcome {
            kind: RuntimeKind::Oci,
            exit_code: output.status.code().unwrap_or(0),
            stdout,
            stderr,
        })
    }

    fn resolve_working_dir(&self) -> Result<PathBuf, RuntimeError> {
        match &self.working_dir {
            Some(path) => {
                if path.exists() {
                    Ok(path.clone())
                } else {
                    Err(RuntimeError::InvalidWorkingDirectory(
                        path.to_string_lossy().into_owned(),
                    ))
                }
            }
            None => Ok(std::env::current_dir()?),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        time::{SystemTime, UNIX_EPOCH},
    };

    fn temp_workdir(name: &str) -> PathBuf {
        let mut path = std::env::temp_dir();
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time is monotonic")
            .as_nanos();
        path.push(format!("silicium-{name}-{unique}"));
        fs::create_dir_all(&path).expect("temp dir");
        path
    }

    #[cfg(feature = "runtime-wasm")]
    #[test]
    fn wasm_runtime_executes_minimal_module() {
        let workdir = temp_workdir("wasm");
        let wasm_path = workdir.join("module.wasm");
        let bytes = wat::parse_str(
            r#"(module
                (func $_start)
                (export "_start" (func $_start))
            )"#,
        )
        .expect("valid wat");
        fs::write(&wasm_path, bytes).expect("write wasm");

        let outcome = RuntimeEnvelope::wasm(Vec::<String>::new())
            .with_module_path(&wasm_path)
            .with_working_dir(&workdir)
            .execute()
            .expect("wasm execution");

        assert_eq!(outcome.kind, RuntimeKind::Wasm);
        assert_eq!(outcome.exit_code, 0);
    }

    #[cfg(not(feature = "runtime-wasm"))]
    #[test]
    fn wasm_runtime_is_explicitly_unavailable_without_feature() {
        let workdir = temp_workdir("wasm");
        let wasm_path = workdir.join("module.wasm");
        fs::write(&wasm_path, b"").expect("write placeholder wasm");

        let err = RuntimeEnvelope::wasm(Vec::<String>::new())
            .with_module_path(&wasm_path)
            .with_working_dir(&workdir)
            .execute()
            .expect_err("wasm runtime should be disabled");

        assert!(matches!(err, RuntimeError::WasmUnavailable));
    }

    #[test]
    fn oci_runtime_requires_image() {
        let workdir = temp_workdir("oci");
        let err = RuntimeEnvelope::oci(vec!["echo".to_string(), "hello".to_string()])
            .with_working_dir(&workdir)
            .execute()
            .expect_err("missing image");

        assert!(matches!(err, RuntimeError::MissingOciImage));
    }
}
