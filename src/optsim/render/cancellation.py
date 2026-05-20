"""Cooperative cancellation for long-running renders."""

from __future__ import annotations

import threading


class RenderCancelled(Exception):
    """Raised when :meth:`RenderCancellation.request` was called mid-render."""


class RenderCancellation:
    """Thread-safe cancellation token shared between UI and renderer."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def request(self) -> None:
        self._event.set()

    def is_requested(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self.is_requested():
            raise RenderCancelled("Render cancelled by user")

    def reset(self) -> None:
        self._event.clear()
