"""
src/notify/base.py
==================
Base notifier interface.

Every notification channel (Discord, email, Slack, etc.) implements
this interface. The pipeline calls notify() on each registered channel.

A notifier failure never fails the core pipeline run.
"""

from abc import ABC, abstractmethod


class BaseNotifier(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable channel name, e.g. 'discord', 'email'."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this channel has all required config (env vars etc.)."""
        ...

    @abstractmethod
    def send(self, opportunities: list[dict], run_id: str) -> bool:
        """
        Send the opportunity list to this channel.

        Args:
            opportunities: list of tender dicts from new_tenders.json
            run_id:        the current pipeline run ID string

        Returns:
            True on success, False on failure.
        """
        ...
