"""Exception hierarchy for rissa.

All errors rissa itself raises derive from :class:`RissaError`, so callers
can catch one base. Subclasses also derive from the matching builtin, so
existing ``except EOFError`` / ``except ValueError`` handlers (including the
test-suite) keep working unchanged.

- :class:`TruncatedError` - file/stream ends mid-field. Never silent partial output.
- :class:`FormatError` - wrong magic, version, backend/transform id, bad
  counts, cross-format feeds (stream bytes to a normal decoder, ...).
- Backend library errors (``lzma.LZMAError``, ``zstandard.ZstdError``) are
  NOT wrapped: they already mean "corrupt payload" precisely.
"""
from __future__ import annotations


class RissaError(Exception):
    """Base for everything rissa raises itself."""


class TruncatedError(RissaError, EOFError):
    """A header, frame, or payload ends before its declared length."""


class FormatError(RissaError, ValueError):
    """Magic, version, id, count, or layout is not a valid .rissa file."""
