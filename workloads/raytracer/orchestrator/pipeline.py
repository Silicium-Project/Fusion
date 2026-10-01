"""Bounded compute/verify scheduler of the fragments of a job.

Each fragment goes through compute then verify. The two stages have their own
in-flight limits and fragments progress independently: a verified fragment
never waits for the others (no global barrier). The stage callbacks are
provided by the caller (see `compute_stage` and `verify_stage`), which keeps
this loop free of network details and easy to test.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable


class RetryFragmentStage:
    """Returned by a poll callback to send the fragment back to its stage queue."""

    def __init__(self, reason: str) -> None:
        self.reason = reason


def run_bounded_fragment_pipeline(
    fragments: list[dict[str, Any]],
    *,
    max_compute_in_flight: int,
    max_verify_in_flight: int,
    launch_compute: Callable[[dict[str, Any]], Any],
    poll_compute: Callable[[dict[str, Any], Any], Any | None],
    launch_verify: Callable[[dict[str, Any], Any], Any],
    poll_verify: Callable[[dict[str, Any], Any, Any], Any | None],
    finish_verify: Callable[[dict[str, Any], Any, Any, Any], None],
    idle: Callable[[], None] = lambda: time.sleep(0.1),
) -> None:
    """Drive independent compute/verify leaves without a global fragment barrier.

    Poll callbacks return None while the task is still running, a
    RetryFragmentStage to requeue the fragment, or the stage result. `idle`
    is called whenever a full sweep made no progress.
    """
    compute_limit = max(1, max_compute_in_flight or len(fragments) or 1)
    verify_limit = max(1, max_verify_in_flight or len(fragments) or 1)
    pending_compute = deque(fragments)
    pending_verify: deque[tuple[dict[str, Any], Any]] = deque()
    computing: list[tuple[dict[str, Any], Any]] = []
    verifying: list[tuple[dict[str, Any], Any, Any]] = []
    finished = 0

    while finished < len(fragments):
        progressed = False
        while pending_compute and len(computing) < compute_limit:
            fragment = pending_compute.popleft()
            computing.append((fragment, launch_compute(fragment)))
            progressed = True

        for fragment, compute_token in list(computing):
            computed = poll_compute(fragment, compute_token)
            if computed is None:
                continue
            computing.remove((fragment, compute_token))
            if isinstance(computed, RetryFragmentStage):
                pending_compute.append(fragment)
                progressed = True
                continue
            pending_verify.append((fragment, computed))
            progressed = True

        while pending_verify and len(verifying) < verify_limit:
            fragment, computed = pending_verify.popleft()
            verifying.append((fragment, computed, launch_verify(fragment, computed)))
            progressed = True

        for fragment, computed, verify_token in list(verifying):
            verified = poll_verify(fragment, computed, verify_token)
            if verified is None:
                continue
            verifying.remove((fragment, computed, verify_token))
            if isinstance(verified, RetryFragmentStage):
                pending_verify.append((fragment, computed))
                progressed = True
                continue
            finish_verify(fragment, computed, verify_token, verified)
            finished += 1
            progressed = True

        if not progressed:
            idle()
