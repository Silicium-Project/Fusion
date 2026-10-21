//! Devnet escrow checks and reward settlement for paid network fragments.
//!
//! The isolated helper reads the worker key from its persistent data volume,
//! constructs and signs Solana transactions, and never returns key material to
//! this process or the logs.

use silicium_node_core::p2p::SolanaPaymentRef;
use std::process::Stdio;
use tokio::process::Command;

const DEFAULT_SETTLEMENT_SCRIPT: &str = "/opt/worker-solana/solana-worker-settlement.mjs";

pub(crate) async fn ready(payment: &SolanaPaymentRef) -> bool {
    run("ready", payment, None).await
}

pub(crate) async fn submit(payment: &SolanaPaymentRef, result_hash: &str) -> bool {
    run("submit", payment, Some(("", result_hash))).await
}

pub(crate) async fn vote(payment: &SolanaPaymentRef, approved: bool) -> bool {
    run(
        "vote",
        payment,
        Some((if approved { "true" } else { "false" }, "")),
    )
    .await
}

async fn run(command: &str, payment: &SolanaPaymentRef, value: Option<(&str, &str)>) -> bool {
    let Some(index) = payment.fragment_index else {
        println!(" Paid task has no on-chain fragment index");
        return false;
    };
    let script = std::env::var("SILICIUM_SOLANA_SETTLEMENT_SCRIPT")
        .unwrap_or_else(|_| DEFAULT_SETTLEMENT_SCRIPT.to_string());
    let mut child = Command::new("node")
        .arg(script)
        .arg(command)
        .arg(&payment.job)
        .arg(payment.expected_fragments.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    match command {
        "ready" => {}
        "submit" => {
            let Some((_, result_hash)) = value else {
                return false;
            };
            child.arg(index.to_string()).arg(result_hash);
        }
        "vote" => {
            let Some((choice, _)) = value else {
                return false;
            };
            child.arg(index.to_string()).arg(choice);
        }
        _ => return false,
    }
    match child.output().await {
        Ok(output) if output.status.success() => true,
        Ok(output) => {
            let reason = String::from_utf8_lossy(&output.stderr);
            let code = reason
                .trim()
                .strip_prefix("worker_settlement_error:")
                .unwrap_or("solana_transaction_failed");
            println!(" Paid task {} settlement failed: {code}", payment.job);
            false
        }
        Err(_) => {
            println!(
                " Paid task {} settlement helper is unavailable",
                payment.job
            );
            false
        }
    }
}
