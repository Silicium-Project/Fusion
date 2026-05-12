use anchor_lang::prelude::*;

use crate::{
    events::{BayesianReputationUpdated, WorkerReputationUpdated},
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

pub const LONG_WEIGHT: u64 = 65;
pub const SHORT_WEIGHT: u64 = 25;
pub const EFFICIENCY_WEIGHT: u64 = 10;

pub const SHORT_DECAY_NUMERATOR: u64 = 9;
pub const SHORT_DECAY_DENOMINATOR: u64 = 10;

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
    // Prior neutre : 5 / 10 = 50%.
    // Important : cela garde la mémoire bayésienne cohérente avec REPUTATION_START = 5_000.
    worker.compute_alpha_long = 5;
    worker.compute_beta_long = 5;
    worker.compute_alpha_short = 5;
    worker.compute_beta_short = 5;

    worker.verify_alpha_long = 5;
    worker.verify_beta_long = 5;
    worker.verify_alpha_short = 5;
    worker.verify_beta_short = 5;

    worker.fraud_strikes = 0;
    worker.error_strikes = 0;
    worker.last_reputation_update = 0;

    worker.performance_score = 5_000;
    worker.efficiency_score = 5_000;
    worker.reliability_score = REPUTATION_START as u32;
    worker.reputation = REPUTATION_START;
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

pub fn recompute_worker_score(worker: &mut Worker, reason: u8) {
    let old_reputation = worker.reputation;

    let compute_long = beta_score(worker.compute_alpha_long, worker.compute_beta_long) as u64;
    let compute_short = beta_score(worker.compute_alpha_short, worker.compute_beta_short) as u64;
    let verify_long = beta_score(worker.verify_alpha_long, worker.verify_beta_long) as u64;
    let verify_short = beta_score(worker.verify_alpha_short, worker.verify_beta_short) as u64;

    let compute_score = compute_long
        .saturating_mul(LONG_WEIGHT)
        .saturating_add(compute_short.saturating_mul(SHORT_WEIGHT))
        .saturating_add((worker.efficiency_score as u64).saturating_mul(EFFICIENCY_WEIGHT))
        .checked_div(100)
        .unwrap_or(0);

    let verify_score = verify_long
        .saturating_mul(LONG_WEIGHT)
        .saturating_add(verify_short.saturating_mul(SHORT_WEIGHT))
        .saturating_add((worker.efficiency_score as u64).saturating_mul(EFFICIENCY_WEIGHT))
        .checked_div(100)
        .unwrap_or(0);

    let combined = compute_score
        .saturating_mul(70)
        .saturating_add(verify_score.saturating_mul(30))
        .checked_div(100)
        .unwrap_or(0);

    let fraud_penalty = (worker.fraud_strikes as u64).saturating_mul(1_500);
    let error_penalty = (worker.error_strikes as u64).saturating_mul(100);

    let final_score = combined
        .saturating_sub(fraud_penalty)
        .saturating_sub(error_penalty)
        .min(REPUTATION_MAX as u64) as i64;

    worker.reliability_score = final_score as u32;
    worker.reputation = final_score.clamp(REPUTATION_MIN, REPUTATION_MAX);

    if worker.reputation <= AUTO_SUSPEND_REPUTATION {
        worker.status = WorkerStatus::Suspended;
    }

    emit!(WorkerReputationUpdated {
        worker: worker.owner,
        old_reputation,
        new_reputation: worker.reputation,
        delta: worker.reputation.saturating_sub(old_reputation),
        reason,
        status: worker.status as u8,
    });

    emit!(BayesianReputationUpdated {
        worker: worker.owner,
        reason,
        reputation: worker.reputation,
        reliability_score: worker.reliability_score,
        compute_alpha_long: worker.compute_alpha_long,
        compute_beta_long: worker.compute_beta_long,
        compute_alpha_short: worker.compute_alpha_short,
        compute_beta_short: worker.compute_beta_short,
        verify_alpha_long: worker.verify_alpha_long,
        verify_beta_long: worker.verify_beta_long,
        verify_alpha_short: worker.verify_alpha_short,
        verify_beta_short: worker.verify_beta_short,
        fraud_strikes: worker.fraud_strikes,
        error_strikes: worker.error_strikes,
    });
}

pub fn update_compute_reputation(worker: &mut Worker, event: ReputationEvent) {
    decay_short_memory(&mut worker.compute_alpha_short, &mut worker.compute_beta_short);

    let reason = match event {
        ReputationEvent::ComputeSuccess => {
            worker.total_verified = worker.total_verified.saturating_add(1);
            worker.compute_alpha_short = worker.compute_alpha_short.saturating_add(2);
            worker.compute_alpha_long = worker.compute_alpha_long.saturating_add(1);
            REP_REASON_COMPUTE_SUCCESS
        }
        ReputationEvent::MinorComputeError => {
            worker.compute_beta_short = worker.compute_beta_short.saturating_add(1);
            worker.error_strikes = worker.error_strikes.saturating_add(1);
            REP_REASON_COMPUTE_FAILED
        }
        ReputationEvent::MajorComputeError => {
            worker.total_rejected = worker.total_rejected.saturating_add(1);
            worker.compute_beta_short = worker.compute_beta_short.saturating_add(3);
            worker.compute_beta_long = worker.compute_beta_long.saturating_add(1);
            worker.error_strikes = worker.error_strikes.saturating_add(1);
            REP_REASON_COMPUTE_FAILED
        }
        ReputationEvent::LateSubmission => {
            worker.compute_beta_short = worker.compute_beta_short.saturating_add(1);
            REP_REASON_CLAIM_TIMEOUT
        }
        ReputationEvent::FraudConfirmed => {
            worker.total_rejected = worker.total_rejected.saturating_add(1);
            worker.compute_beta_short = worker.compute_beta_short.saturating_add(25);
            worker.compute_beta_long = worker.compute_beta_long.saturating_add(10);
            worker.fraud_strikes = worker.fraud_strikes.saturating_add(1);
            REP_REASON_FRAUD
        }
        _ => REP_REASON_COMPUTE_FAILED,
    };

    worker.last_reputation_update = Clock::get().map(|c| c.unix_timestamp).unwrap_or(0);
    recompute_worker_score(worker, reason);
}

pub fn update_verify_reputation(worker: &mut Worker, event: ReputationEvent) {
    decay_short_memory(&mut worker.verify_alpha_short, &mut worker.verify_beta_short);

    let reason = match event {
        ReputationEvent::VerificationSuccess => {
            worker.total_verified = worker.total_verified.saturating_add(1);
            worker.verify_alpha_short = worker.verify_alpha_short.saturating_add(2);
            worker.verify_alpha_long = worker.verify_alpha_long.saturating_add(1);
            REP_REASON_VOTE_CORRECT
        }
        ReputationEvent::WrongVerification => {
            worker.total_rejected = worker.total_rejected.saturating_add(1);
            worker.verify_beta_short = worker.verify_beta_short.saturating_add(3);
            worker.verify_beta_long = worker.verify_beta_long.saturating_add(1);
            worker.error_strikes = worker.error_strikes.saturating_add(1);
            REP_REASON_VOTE_WRONG
        }
        ReputationEvent::MaliciousVerification => {
            worker.total_rejected = worker.total_rejected.saturating_add(1);
            worker.verify_beta_short = worker.verify_beta_short.saturating_add(20);
            worker.verify_beta_long = worker.verify_beta_long.saturating_add(8);
            worker.fraud_strikes = worker.fraud_strikes.saturating_add(1);
            REP_REASON_SLASH
        }
        _ => REP_REASON_VOTE_WRONG,
    };

    worker.last_reputation_update = Clock::get().map(|c| c.unix_timestamp).unwrap_or(0);
    recompute_worker_score(worker, reason);
}

// Compatibilité avec les instructions V1 existantes.
pub fn apply_reputation_delta(worker: &mut Worker, delta: i64, reason: u8) {
    let old_reputation = worker.reputation;
    let next = old_reputation.saturating_add(delta);

    worker.reputation = next.clamp(REPUTATION_MIN, REPUTATION_MAX);
    worker.reliability_score = worker.reputation as u32;

    if worker.reputation <= AUTO_SUSPEND_REPUTATION {
        worker.status = WorkerStatus::Suspended;
    }

    emit!(WorkerReputationUpdated {
        worker: worker.owner,
        old_reputation,
        new_reputation: worker.reputation,
        delta,
        reason,
        status: worker.status as u8,
    });
}

pub fn record_compute_success(worker: &mut Worker) {
    update_compute_reputation(worker, ReputationEvent::ComputeSuccess);
}

pub fn record_compute_failure(worker: &mut Worker) {
    update_compute_reputation(worker, ReputationEvent::MajorComputeError);
}

pub fn record_claim_timeout(worker: &mut Worker) {
    update_compute_reputation(worker, ReputationEvent::LateSubmission);
}

pub fn record_vote_correct(worker: &mut Worker) {
    update_verify_reputation(worker, ReputationEvent::VerificationSuccess);
}

pub fn record_vote_wrong(worker: &mut Worker) {
    update_verify_reputation(worker, ReputationEvent::WrongVerification);
}

pub fn record_slash(worker: &mut Worker) {
    update_verify_reputation(worker, ReputationEvent::MaliciousVerification);
}
