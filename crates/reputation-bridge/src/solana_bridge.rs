use serde::{Deserialize, Serialize};

/// Calls the Solana JSON-RPC API directly — no OpenSSL dependency.
/// Replaces the `solana-client` crate to avoid native TLS requirements on Windows.
pub struct SolanaManager {
    rpc_url: String,
    client: reqwest::Client,
}

#[derive(Debug, Serialize)]
struct RpcRequest<'a> {
    jsonrpc: &'a str,
    id: u64,
    method: &'a str,
    params: serde_json::Value,
}

#[derive(Debug, Deserialize)]
struct RpcResponse {
    result: Option<BalanceResult>,
    error: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct BalanceResult {
    value: u64,
}

impl SolanaManager {
    pub fn new(rpc_url: &str) -> Self {
        let url = if rpc_url.is_empty() {
            "https://api.mainnet-beta.solana.com"
        } else {
            rpc_url
        };
        Self {
            rpc_url: url.to_string(),
            client: reqwest::Client::new(),
        }
    }

    /// Validates a base58 Solana address (32-byte public key).
    fn validate_address(wallet_address: &str) -> Result<(), String> {
        let decoded = bs58::decode(wallet_address)
            .into_vec()
            .map_err(|e| format!("Invalid base58 address: {e}"))?;
        if decoded.len() != 32 {
            return Err(format!(
                "Invalid Solana pubkey length: expected 32 bytes, got {}",
                decoded.len()
            ));
        }
        Ok(())
    }

    /// Returns true if the wallet's lamport balance >= min_stake.
    /// Uses getBalance JSON-RPC call directly.
    pub async fn verify_stake(&self, wallet_address: &str, min_stake: u64) -> Result<bool, String> {
        Self::validate_address(wallet_address)?;

        let request = RpcRequest {
            jsonrpc: "2.0",
            id: 1,
            method: "getBalance",
            params: serde_json::json!([
                wallet_address,
                { "commitment": "finalized" }
            ]),
        };

        let response: RpcResponse = self
            .client
            .post(&self.rpc_url)
            .json(&request)
            .send()
            .await
            .map_err(|e| format!("RPC request failed: {e}"))?
            .json()
            .await
            .map_err(|e| format!("RPC response parse error: {e}"))?;

        if let Some(err) = response.error {
            return Err(format!("Solana RPC error: {err}"));
        }

        let balance = response
            .result
            .ok_or_else(|| "Empty RPC result".to_string())?
            .value;

        tracing::info!(
            wallet = wallet_address,
            balance_lamports = balance,
            min_stake,
            "Stake verification"
        );

        Ok(balance >= min_stake)
    }
}

// ── Request / Response DTOs ───────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct StakeQuery {
    pub wallet: String,
    pub min_stake: u64,
}

#[derive(Debug, Serialize)]
pub struct StakeResponse {
    pub ok: bool,
    pub balance_meets_threshold: bool,
    pub wallet: String,
}
