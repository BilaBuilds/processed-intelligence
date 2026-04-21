"""
outreach package
================
Manual outreach helpers for previewing and sending weekly sample bundles
from existing tender pipeline outputs.
"""

from outreach.service import preview_sample_for_contact, send_sample_to_contact

__all__ = ["preview_sample_for_contact", "send_sample_to_contact"]
