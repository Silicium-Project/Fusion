//! Billing derived from finalized tasks: the publisher pays the claimant of
//! the finalized attempt (`reward`) and each counted verifier
//! (`verifier_reward`, the first `verifications_required` approvals by
//! event hash). Every peer computes the same settlements from the same book.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use super::{DerivedTaskStatus, TaskBook, TaskEventBody};

/// Why a payment is due.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SettlementRole {
    Worker,
    Verifier,
}

/// One payment due from `payer` (publisher) to `payee`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Settlement {
    pub task_id: String,
    pub attempt: u32,
    pub payer: String,
    pub payee: String,
    pub role: SettlementRole,
    pub amount: u64,
}

impl TaskBook {
    /// Payments due for `task_id`, empty unless it is finalized.
    pub fn settlements_for(&self, task_id: &str) -> Vec<Settlement> {
        // Finalization does not depend on time: any instant gives the same answer.
        let Some(state) = self.task_state(task_id, 0) else {
            return Vec::new();
        };
        let (DerivedTaskStatus::Finalized, Some(attempt)) = (state.status, state.finalized_attempt)
        else {
            return Vec::new();
        };
        let Some(finalized) = state.attempts.get(attempt as usize - 1) else {
            return Vec::new();
        };
        let payment = |payee: &str, role, amount| Settlement {
            task_id: task_id.to_string(),
            attempt,
            payer: state.publisher.clone(),
            payee: payee.to_string(),
            role,
            amount,
        };
        let mut due = vec![payment(
            &finalized.claimant,
            SettlementRole::Worker,
            state.terms.reward,
        )];
        if let Some(result) = &finalized.result {
            let counted = result
                .approvals
                .iter()
                .take(state.terms.verifications_required as usize);
            for (_, verifier) in counted {
                due.push(payment(
                    verifier,
                    SettlementRole::Verifier,
                    state.terms.verifier_reward,
                ));
            }
        }
        due
    }

    /// Payments due for every finalized task, by task identifier.
    pub fn settlements(&self) -> Vec<Settlement> {
        let mut task_ids: Vec<&str> = self
            .events
            .values()
            .filter(|event| matches!(event.body, TaskEventBody::TaskFinalized { .. }))
            .map(|event| event.task_id.as_str())
            .collect();
        task_ids.sort_unstable();
        task_ids.dedup();
        task_ids
            .into_iter()
            .flat_map(|task_id| self.settlements_for(task_id))
            .collect()
    }

    /// Net balance per author (received minus paid) over all settlements.
    pub fn balances(&self) -> BTreeMap<String, i128> {
        let mut balances = BTreeMap::new();
        for settlement in self.settlements() {
            *balances.entry(settlement.payee).or_insert(0) += i128::from(settlement.amount);
            *balances.entry(settlement.payer).or_insert(0) -= i128::from(settlement.amount);
        }
        balances
    }
}
