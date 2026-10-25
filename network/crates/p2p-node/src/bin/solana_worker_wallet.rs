//! Create and inspect the Devnet-only Solana signer kept in a miniworker's
//! private Docker data volume. The key is written in Solana CLI JSON format
//! and is never printed; stdout contains only the public address.

use ed25519_dalek::SigningKey;
use std::{
    error::Error,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::Path,
};

fn main() {
    if let Err(error) = run() {
        eprintln!("solana-worker-wallet: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let command = args.next().unwrap_or_default();
    let path = args
        .next()
        .unwrap_or_else(|| "/data/solana-wallet.json".into());
    if args.next().is_some() || !matches!(command.as_str(), "ensure" | "pubkey") {
        return Err("usage: solana-worker-wallet {ensure|pubkey} [keypair.json]".into());
    }

    let path = Path::new(&path);
    if command == "ensure" {
        ensure_keypair(path)?;
    }
    let keypair = read_keypair(path)?;
    let key = SigningKey::from_keypair_bytes(&keypair)?;
    println!(
        "{}",
        bs58::encode(key.verifying_key().to_bytes()).into_string()
    );
    Ok(())
}

fn ensure_keypair(path: &Path) -> Result<(), Box<dyn Error>> {
    if path.exists() {
        // Validate an existing file before preserving it across restarts.
        let _ = read_keypair(path)?;
        set_private_permissions(path)?;
        return Ok(());
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    let mut seed = [0_u8; 32];
    File::open("/dev/urandom")?.read_exact(&mut seed)?;
    let bytes = SigningKey::from_bytes(&seed).to_keypair_bytes();
    seed.fill(0);
    let encoded = serde_json::to_vec(&bytes.to_vec())?;

    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    match options.open(path) {
        Ok(mut file) => file.write_all(&encoded)?,
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            // Two processes may start against the same volume at once.
            let _ = read_keypair(path)?;
        }
        Err(error) => return Err(error.into()),
    }
    set_private_permissions(path)?;
    Ok(())
}

fn read_keypair(path: &Path) -> Result<[u8; 64], Box<dyn Error>> {
    let metadata = fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("wallet path must be a regular file, not a symlink".into());
    }
    let values: Vec<u8> = serde_json::from_slice(&fs::read(path)?)?;
    let bytes: [u8; 64] = values
        .try_into()
        .map_err(|_| "wallet JSON must contain exactly 64 bytes")?;
    SigningKey::from_keypair_bytes(&bytes)
        .map_err(|_| "wallet public key does not match its private key")?;
    Ok(bytes)
}

fn set_private_permissions(path: &Path) -> Result<(), Box<dyn Error>> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}
