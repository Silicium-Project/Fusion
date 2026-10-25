/** A private qualification is bounded by an owner-controlled SHA/time window and GitHub's zero spend stop. */
import { Failure } from './process.mjs';
export function requireZeroActionsBudget(budgets) {
  const matches = budgets.filter(
    (b) => b.budget_scope === 'organization' && b.budget_product_sku === 'actions',
  );
  if (
    !matches.length ||
    !matches.some((b) => b.budget_amount === 0 && b.prevent_further_usage === true)
  )
    throw new Failure('A zero Actions organization budget with usage prevention is required', 4);
  return { product: 'actions', scope: 'organization', amount: 0, prevent_further_usage: true };
}
export function privateQualificationWindow(head, minutes = 180, now = Date.now()) {
  if (!/^[a-f0-9]{40}$/.test(head) || !Number.isInteger(minutes) || minutes < 1 || minutes > 240)
    throw new Failure('Exact SHA and a window of at most 240 minutes required', 2);
  return {
    schema_version: 1,
    head_sha: head,
    budget_verified_at: new Date(now).toISOString(),
    expires_at: new Date(now + minutes * 60_000).toISOString(),
    actions_budget: 0,
    prevent_further_usage: true,
  };
}
export function validatePrivateWindow(window, head, now = Date.now()) {
  const verified = Date.parse(window?.budget_verified_at),
    expires = Date.parse(window?.expires_at);
  if (
    window?.schema_version !== 1 ||
    window.head_sha !== head ||
    window.actions_budget !== 0 ||
    window.prevent_further_usage !== true ||
    !Number.isFinite(verified) ||
    !Number.isFinite(expires) ||
    verified > now + 60_000 ||
    expires <= now ||
    expires - verified > 240 * 60_000 ||
    expires <= verified
  )
    throw new Failure('Private qualification is absent, expired or belongs to another commit', 4);
  return true;
}
