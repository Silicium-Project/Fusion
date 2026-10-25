use anchor_lang::prelude::*;

use crate::{
    events::{BayesianReputationUpdated, DualReputationUpdated},
    state::worker::{Worker, WorkerStatus},
};

pub const REPUTATION_MIN: i64 = 0;
pub const REPUTATION_MAX: i64 = 10_000;
pub const REPUTATION_START: i64 = 5_000;
pub const REPUTATION_SCALE: i64 = 10_000;

pub const MIN_COMPUTE_REPUTATION: i64 = 1_500;
pub const MIN_VERIFY_REPUTATION: i64 = 2_500;

pub const AUTO_SUSPEND_REPUTATION: i64 = 1_000;

pub const REP_REASON_COMPUTE_SUCCESS: u8 = 1;
pub const REP_REASON_COMPUTE_FAILED: u8 = 2;
pub const REP_REASON_CLAIM_TIMEOUT: u8 = 3;
pub const REP_REASON_VOTE_CORRECT: u8 = 4;
pub const REP_REASON_VOTE_WRONG: u8 = 5;
pub const REP_REASON_SLASH: u8 = 6;
pub const REP_REASON_FRAUD: u8 = 7;

pub const COMPUTE_LONG_WEIGHT: u64 = 65;
pub const COMPUTE_SHORT_WEIGHT: u64 = 25;
pub const COMPUTE_EFFICIENCY_WEIGHT: u64 = 10;

pub const VERIFY_LONG_WEIGHT: u64 = 70;
pub const VERIFY_SHORT_WEIGHT: u64 = 30;

pub const GLOBAL_COMPUTE_WEIGHT: u64 = 50;
pub const GLOBAL_VERIFY_WEIGHT: u64 = 50;

pub const SHORT_DECAY_NUMERATOR: u64 = 9;
pub const SHORT_DECAY_DENOMINATOR: u64 = 10;

/// Minimum vote impact of a new verifier.
/// A verifier with 0 verify reputation still has 25% weight so the network can bootstrap.
pub const MIN_VERIFIER_WEIGHT_BPS: u64 = 2_500;
pub const BPS_DENOMINATOR: u64 = 10_000;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum ReputationEvent {
    ComputeSuccess,
    MinorComputeError,
    MajorComputeError,
    LateSubmission,
    FraudConfirmed,
    VerificationSuccess,
    WrongVerification,
    MaliciousVerification,
}

pub fn init_bayesian_reputation(worker: &mut Worker) {
    // V2.5 bootstrap: everyone starts neutral, not trusted and not punished.
    // 5 / (5 + 5) = 50%.
    worker.compute_alpha_long = 5;
    worker.compute_beta_long = 5;
    worker.compute_alpha_short = 5;
    worker.compute_beta_short = 5;

    worker.verify_alpha_long = 5;
    worker.verify_beta_long = 5;
    worker.verify_alpha_short = 5;
    worker.verify_beta_short = 5;

    worker.compute_reputation = REPUTATION_START;
    worker.verify_reputation = REPUTATION_START;
    worker.global_reputation = REPUTATION_START;

    worker.compute_jobs_done = 0;
    worker.verify_jobs_done = 0;
    worker.compute_failures = 0;
    worker.verify_failures = 0;

    worker.compute_fraud_strikes = 0;
    worker.verify_fraud_strikes = 0;
    worker.fraud_strikes = 0;
    worker.error_strikes = 0;
    worker.last_reputation_update = 0;

    worker.performance_score = 5_000;
    worker.efficiency_score = 5_000;
    worker.reliability_score = REPUTATION_START as u32;
}

pub fn beta_score(alpha: u64, beta: u64) -> i64 {
    let total = alpha.saturating_add(beta);

    if total == 0 {
        return REPUTATION_START;
    }

    let score = (alpha as u128)
        .saturating_mul(REPUTATION_SCALE as u128)
        .checked_div(total as u128)
        .unwrap_or(0);

    score.min(REPUTATION_SCALE as u128) as i64
}

pub fn decay_short_memory(alpha: &mut u64, beta: &mut u64) {
    *alpha = alpha
        .saturating_mul(SHORT_DECAY_NUMERATOR)
        .checked_div(SHORT_DECAY_DENOMINATOR)
        .unwrap_or(*alpha);

    *beta = beta
        .saturating_mul(SHORT_DECAY_NUMERATOR)
        .checked_div(SHORT_DECAY_DENOMINATOR)
        .unwrap_or(*beta);

    if *alpha < 1 {
        *alpha = 1;
    }

    if *beta < 1 {
        *beta = 1;
    }
}

pub fn verifier_weight_bps(verifier_reputation: i64) -> u64 {
    let rep = verifier_reputation.clamp(REPUTATION_MIN, REPUTATION_MAX) as u64;

    MIN_VERIFIER_WEIGHT_BPS.saturating_add(
        rep.saturating_mul(BPS_DENOMINATOR.saturating_sub(MIN_VERIFIER_WEIGHT_BPS))
            .checked_div(BPS_DENOMINATOR)
            .unwrap_or(0),
    )
}

pub fn weighted_amount(base: u64, weight_bps: u64) -> u64 {
    let amount = base
        .saturating_mul(weight_bps)
        .checked_div(BPS_DENOMINATOR)
        .unwrap_or(0);

    amount.max(1)
}

pub fn recompute_worker_score(worker: &mut Worker, reason: u8) {
    let old_compute_reputation = worker.compute_reputation;
    let old_verify_reputation = worker.verify_reputation;

    let compute_long = beta_score(worker.compute_alpha_long, worker.compute_beta_long) as u64;
    let compute_short = beta_score(worker.compute_alpha_short, worker.compute_beta_short) as u64;
    let verify_long = beta_score(worker.verify_alpha_long, worker.verify_beta_long) as u64;
    let verify_short = beta_score(worker.verify_alpha_short, worker.verify_beta_short) as u64;

    let compute_raw = compute_long
        .saturating_mul(COMPUTE_LONG_WEIGHT)
        .saturating_add(compute_short.saturating_mul(COMPUTE_SHORT_WEIGHT))
        .saturating_add((worker.efficiency_score as u64).saturating_mul(COMPUTE_EFFICIENCY_WEIGHT))
        .checked_div(100)
        .unwrap_or(0);

    let verify_raw = verify_long
        .saturating_mul(VERIFY_LONG_WEIGHT)
        .saturating_add(verify_short.saturating_mul(VERIFY_SHORT_WEIGHT))
        .checked_div(100)
        .unwrap_or(0);

    let compute_penalty = (worker.compute_fraud_strikes as u64)
        .saturating_mul(1_500)
        .saturating_add(worker.compute_failures.saturating_mul(25));

    let verify_penalty = (worker.verify_fraud_strikes as u64)
        .saturating_mul(1_500)
        .saturating_add(worker.verify_failures.saturating_mul(25));

    let compute_score = compute_raw
        .saturating_sub(compute_penalty)
        .min(REPUTATION_MAX as u64) as i64;

    let verify_score = verify_raw
        .saturating_sub(verify_penalty)
        .min(REPUTATION_MAX as u64) as i64;

    let global = (compute_score as u64)
        .saturating_mul(GLOBAL_COMPUTE_WEIGHT)
        .saturating_add((verify_score as u64).saturating_mul(GLOBAL_VERIFY_WEIGHT))
        .checked_div(100)
        .unwrap_or(0)
        .min(REPUTATION_MAX as u64) as i64;

    worker.compute_reputation = compute_score.clamp(REPUTATION_MIN, REPUTATION_MAX);
    worker.verify_reputation = verify_score.clamp(REPUTATION_MIN, REPUTATION_MAX);
    worker.global_reputation = global.clamp(REPUTATION_MIN, REPUTATION_MAX);

    worker.reliability_score = worker.global_reputation as u32;
    worker.fraud_strikes = worker
        .compute_fraud_strikes
        .saturating_add(worker.verify_fraud_strikes);

    if worker.global_reputation <= AUTO_SUSPEND_REPUTATION {
        worker.status = WorkerStatus::Suspended;
    }

    emit!(DualReputationUpdated {
        worker: worker.owner,
        old_compute_reputation,
        new_compute_reputation: worker.compute_reputation,
        old_verify_reputation,
        new_verify_reputation: worker.verify_reputation,
        global_reputation: worker.global_reputation,
        reason,
        status: worker.status as u8,
    });

    emit!(BayesianReputationUpdated {
        worker: worker.owner,
        reason,
        compute_reputation: worker.compute_reputation,
        verify_reputation: worker.verify_reputation,
        global_reputation: worker.global_reputation,
        reliability_score: worker.reliability_score,
        compute_alpha_long: worker.compute_alpha_long,
        compute_beta_long: worker.compute_beta_long,
        compute_alpha_short: worker.compute_alpha_short,
        compute_beta_short: worker.compute_beta_short,
        verify_alpha_long: worker.verify_alpha_long,
        verify_beta_long: worker.verify_beta_long,
        verify_alpha_short: worker.verify_alpha_short,
        verify_beta_short: worker.verify_beta_short,
        compute_fraud_strikes: worker.compute_fraud_strikes,
        verify_fraud_strikes: worker.verify_fraud_strikes,
        fraud_strikes: worker.fraud_strikes,
        error_strikes: worker.error_strikes,
    });
}

pub fn update_compute_reputation(worker: &mut Worker, event: ReputationEvent) {
    update_compute_reputation_with_weight(worker, event, BPS_DENOMINATOR);
}

pub fn update_compute_reputation_weighted(
    worker: &mut Worker,
    event: ReputationEvent,
    verifier_reputation: i64,
) {
    let weight = verifier_weight_bps(verifier_reputation);
    update_compute_reputation_with_weight(worker, event, weight);
}

fn update_compute_reputation_with_weight(
    worker: &mut Worker,
    event: ReputationEvent,
    weight_bps: u64,
) {
    decay_short_memory(
        &mut worker.compute_alpha_short,
        &mut worker.compute_beta_short,
    );

    let reason = match event {
        ReputationEvent::ComputeSuccess => {
            worker.total_verified = worker.total_verified.saturating_add(1);
            worker.compute_jobs_done = worker.compute_jobs_done.saturating_add(1);
            worker.compute_alpha_short = worker.compute_alpha_short.saturating_add(2);
            worker.compute_alpha_long = worker.compute_alpha_long.saturating_add(1);
            REP_REASON_COMPUTE_SUCCESS
        }
        ReputationEvent::MinorComputeError => {
            worker.compute_beta_short = worker
                .compute_beta_short
                .saturating_add(weighted_amount(1, weight_bps));
            worker.compute_failures = worker.compute_failures.saturating_add(1);
            worker.error_strikes = worker.error_strikes.saturating_add(1);
            REP_REASON_COMPUTE_FAILED
        }
        ReputationEvent::MajorComputeError => {
            worker.total_rejected = worker.total_rejected.saturating_add(1);
            worker.compute_beta_short = worker
                .compute_beta_short
                .saturating_add(weighted_amount(4, weight_bps));
            worker.compute_beta_long = worker
                .compute_beta_long
                .saturating_add(weighted_amount(1, weight_bps));
            worker.compute_failures = worker.compute_failures.saturating_add(1);
            worker.error_strikes = worker.error_strikes.saturating_add(1);
            REP_REASON_COMPUTE_FAILED
        }
        ReputationEvent::LateSubmission => {
            worker.compute_beta_short = worker.compute_beta_short.saturating_add(1);
            worker.compute_failures = worker.compute_failures.saturating_add(1);
            REP_REASON_CLAIM_TIMEOUT
        }
        ReputationEvent::FraudConfirmed => {
            worker.total_rejected = worker.total_rejected.saturating_add(1);
            worker.compute_beta_short = worker
                .compute_beta_short
                .saturating_add(weighted_amount(30, weight_bps));
            worker.compute_beta_long = worker
                .compute_beta_long
                .saturating_add(weighted_amount(12, weight_bps));
            worker.compute_fraud_strikes = worker.compute_fraud_strikes.saturating_add(1);
            REP_REASON_FRAUD
        }
        _ => REP_REASON_COMPUTE_FAILED,
    };

    worker.last_reputation_update = Clock::get().map(|c| c.unix_timestamp).unwrap_or(0);
    recompute_worker_score(worker, reason);
}

pub fn update_verify_reputation(worker: &mut Worker, event: ReputationEvent) {
    decay_short_memory(
        &mut worker.verify_alpha_short,
        &mut worker.verify_beta_short,
    );

    let reason = match event {
        ReputationEvent::VerificationSuccess => {
            worker.total_verified = worker.total_verified.saturating_add(1);
            worker.verify_jobs_done = worker.verify_jobs_done.saturating_add(1);
            worker.verify_alpha_short = worker.verify_alpha_short.saturating_add(2);
            worker.verify_alpha_long = worker.verify_alpha_long.saturating_add(1);
            REP_REASON_VOTE_CORRECT
        }
        ReputationEvent::WrongVerification => {
            worker.total_rejected = worker.total_rejected.saturating_add(1);
            worker.verify_beta_short = worker.verify_beta_short.saturating_add(3);
            worker.verify_beta_long = worker.verify_beta_long.saturating_add(1);
            worker.verify_failures = worker.verify_failures.saturating_add(1);
            worker.error_strikes = worker.error_strikes.saturating_add(1);
            REP_REASON_VOTE_WRONG
        }
        ReputationEvent::MaliciousVerification => {
            worker.total_rejected = worker.total_rejected.saturating_add(1);
            worker.verify_beta_short = worker.verify_beta_short.saturating_add(20);
            worker.verify_beta_long = worker.verify_beta_long.saturating_add(8);
            worker.verify_fraud_strikes = worker.verify_fraud_strikes.saturating_add(1);
            REP_REASON_SLASH
        }
        _ => REP_REASON_VOTE_WRONG,
    };

    worker.last_reputation_update = Clock::get().map(|c| c.unix_timestamp).unwrap_or(0);
    recompute_worker_score(worker, reason);
}
