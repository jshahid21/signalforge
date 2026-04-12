"""Graceful @traceable decorator — no-op when langsmith is not installed."""
from __future__ import annotations

try:
    from langsmith import traceable  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover – langsmith is an optional dependency
    from functools import wraps
    from typing import Any, Callable, TypeVar

    F = TypeVar("F", bound=Callable[..., Any])

    def traceable(func: F | None = None, *, name: str = "", **kwargs: Any) -> Any:  # noqa: ARG001
        """No-op stand-in for @traceable when langsmith is not installed."""
        if func is None:
            return lambda f: f
        return func
