"""Bounded retry policies for safe/idempotent and non-idempotent operations."""

from __future__ import annotations

import time
from typing import Callable, TypeVar, Any

T = TypeVar("T")


def execute_with_retry(
    fn: Callable[[], T],
    is_idempotent: bool = True,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> T:
    """Execute a function with bounded retries for idempotent operations and zero retries for submissions.
    
    Args:
        fn: Callable function to execute.
        is_idempotent: If True, allow retries. If False (e.g. form submission), attempt exactly once.
        max_retries: Maximum number of retries for idempotent calls.
        backoff_seconds: Initial backoff duration in seconds.
        
    Returns:
        Result of the callable function.
        
    Raises:
        Exception: The last exception raised by fn if all attempts fail.
    """
    attempts = max_retries if is_idempotent else 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < attempts:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))
            else:
                break

    if last_error:
        raise last_error
    raise RuntimeError("Execution failed without producing an exception.")
