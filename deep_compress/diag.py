"""Diagnosis policy for suppressed transform/backend errors.

Default: noisy-but-safe. A failing transform candidate is skipped (valid but
possibly suboptimal output) and recorded at debug level — never silently
dropped without a trace.

RISSA_STRICT=1: re-raise immediately. Use for debugging, benchmarking new
transforms, and CI. A red CI run under RISSA_STRICT means a transform is
broken, not that the input is hard.
"""
import logging
import os

LOG = logging.getLogger("rissa.mdl")


def strict():
    return os.environ.get("RISSA_STRICT") == "1"


def note(where, exc):
    """Record a skipped candidate. Re-raises under RISSA_STRICT=1."""
    if strict():
        raise exc
    LOG.debug("%s skipped: %s: %s", where, type(exc).__name__, exc)
