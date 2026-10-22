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
    run("ready", payment, &[]).await
}

pub(crate) async fn submit(payment: &SolanaPaymentRef, result_hash: &str) -> bool {
    let Some(index) = payment.fragment_index else {
        return false;
    };
    run(
        "submit",
        payment,
        &[index.to_string(), result_hash.to_string()],
    )
    .await
}

pub(crate) async fn vote(payment: &SolanaPaymentRef, approved: bool) -> bool {
    let Some(index) = payment.fragment_index else {
        return false;
    };
    run("vote", payment, &[index.to_string(), approved.to_string()]).await
}

pub(crate) async fn split(
    payment: &SolanaPaymentRef,
    manifest_hash: &str,
    children: &[(u32, String); 2],
) -> bool {
    let Some(index) = payment.fragment_index else {
        return false;
    };
    run(
        "split",
        payment,
        &[
            index.to_string(),
            manifest_hash.to_string(),
            children[0].0.to_string(),
            children[0].1.clone(),
            children[1].0.to_string(),
            children[1].1.clone(),
        ],
    )
    .await
}

async fn run(command: &str, payment: &SolanaPaymentRef, args: &[String]) -> bool {
    let script = std::env::var("SILICIUM_SOLANA_SETTLEMENT_SCRIPT")
        .unwrap_or_else(|_| DEFAULT_SETTLEMENT_SCRIPT.to_string());
    let mut child = Command::new("node");
    child
        .arg(script)
        .arg(command)
        .arg(&payment.job)
        .arg(payment.expected_fragments.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    child.args(args);
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
