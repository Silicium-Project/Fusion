use anchor_lang::prelude::*;

use crate::{
    events::WorkerReputationUpdated,
    state::worker::{Worker, WorkerStatus},
};

pub const REPUTATION_MIN: i64 = 0;
pub const REPUTATION_MAX: i64 = 10_000;
pub const REPUTATION_START: i64 = 5_000;

pub const MIN_COMPUTE_REPUTATION: i64 = 1_500;
pub const MIN_VERIFY_REPUTATION: i64 = 2_500;

pub const REP_COMPUTE_SUCCESS: i64 = 80;
pub const REP_COMPUTE_FAILED: i64 = -250;
pub const REP_CLAIM_TIMEOUT: i64 = -120;
pub const REP_VOTE_CORRECT: i64 = 40;
pub const REP_VOTE_WRONG: i64 = -180;
pub const REP_SLASH_EXTRA: i64 = -300;

pub const AUTO_SUSPEND_REPUTATION: i64 = 1_000;

pub const REP_REASON_COMPUTE_SUCCESS: u8 = 1;
pub const REP_REASON_COMPUTE_FAILED: u8 = 2;
pub const REP_REASON_CLAIM_TIMEOUT: u8 = 3;
pub const REP_REASON_VOTE_CORRECT: u8 = 4;
pub const REP_REASON_VOTE_WRONG: u8 = 5;
pub const REP_REASON_SLASH: u8 = 6;

pub fn apply_reputation_delta(worker: &mut Worker, delta: i64, reason: u8) {
    let old_reputation = worker.reputation;
    let next = old_reputation.saturating_add(delta);

    worker.reputation = next.clamp(REPUTATION_MIN, REPUTATION_MAX);

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
    worker.total_verified = worker.total_verified.saturating_add(1);
    apply_reputation_delta(worker, REP_COMPUTE_SUCCESS, REP_REASON_COMPUTE_SUCCESS);
}

pub fn record_compute_failure(worker: &mut Worker) {
    worker.total_rejected = worker.total_rejected.saturating_add(1);
    apply_reputation_delta(worker, REP_COMPUTE_FAILED, REP_REASON_COMPUTE_FAILED);
}

pub fn record_claim_timeout(worker: &mut Worker) {
    apply_reputation_delta(worker, REP_CLAIM_TIMEOUT, REP_REASON_CLAIM_TIMEOUT);
}

pub fn record_vote_correct(worker: &mut Worker) {
    worker.total_verified = worker.total_verified.saturating_add(1);
    apply_reputation_delta(worker, REP_VOTE_CORRECT, REP_REASON_VOTE_CORRECT);
}

pub fn record_vote_wrong(worker: &mut Worker) {
    worker.total_rejected = worker.total_rejected.saturating_add(1);
    apply_reputation_delta(worker, REP_VOTE_WRONG, REP_REASON_VOTE_WRONG);
}

pub fn record_slash(worker: &mut Worker) {
    apply_reputation_delta(worker, REP_SLASH_EXTRA, REP_REASON_SLASH);
}
