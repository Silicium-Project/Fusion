/** Owner-approved sole-maintainer policy; production approvals are configured separately. */
import { repository } from './github.mjs';
import { Failure } from './process.mjs';

export function mainProtection() {
  return {
    required_status_checks: {
      strict: true,
      checks: [{ context: 'ci/required', app_id: 15368 }],
    },
    enforce_admins: true,
    required_pull_request_reviews: {
      dismiss_stale_reviews: true,
      require_code_owner_reviews: false,
      required_approving_review_count: 0,
      require_last_push_approval: false,
    },
    restrictions: null,
    required_conversation_resolution: true,
    allow_force_pushes: false,
    allow_deletions: false,
  };
}

export function soleMaintainerRules(ruleset) {
  const refs = ruleset.conditions?.ref_name?.include;
  if (
    ruleset.source_type !== 'Repository' ||
    ruleset.source !== repository ||
    ruleset.target !== 'branch' ||
    !refs?.length ||
    refs.some((ref) => !['~DEFAULT_BRANCH', 'refs/heads/main'].includes(ref))
  )
    throw new Failure(
      'Split inherited or shared rulesets before changing the main review policy',
      3,
    );
  return ruleset.rules.map((rule) =>
    rule.type === 'pull_request'
      ? {
          ...rule,
          parameters: {
            ...rule.parameters,
            required_approving_review_count: 0,
            require_code_owner_review: false,
            require_last_push_approval: false,
            require_extra_approval_for_unattributed_changes: false,
            required_reviewers: [],
          },
        }
      : rule,
  );
}

export function verifyMainProtection(current, effectiveRules) {
  const review = current.required_pull_request_reviews;
  if (
    current.enforce_admins?.enabled !== true ||
    current.required_conversation_resolution?.enabled !== true ||
    current.required_status_checks?.strict !== true ||
    !current.required_status_checks?.checks?.some(
      (check) => check.context === 'ci/required' && check.app_id === 15368,
    ) ||
    current.allow_force_pushes?.enabled !== false ||
    current.allow_deletions?.enabled !== false ||
    review?.required_approving_review_count !== 0 ||
    review.require_code_owner_reviews !== false ||
    review.require_last_push_approval !== false ||
    effectiveRules.some(
      (rule) =>
        rule.type === 'pull_request' &&
        (rule.parameters.required_approving_review_count !== 0 ||
          rule.parameters.require_code_owner_review ||
          rule.parameters.require_last_push_approval ||
          rule.parameters.require_extra_approval_for_unattributed_changes ||
          rule.parameters.required_reviewers?.length),
    )
  )
    throw new Failure('Main protection verification failed; do not merge or publish', 3);
}
