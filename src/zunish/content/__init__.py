"""Extensible content libraries: chord progressions, scales, riffs, rhythms,
and accompaniment patterns. Each submodule owns one :class:`~zunish.registry.Registry`
and registers its built-in entries at import time. Add new elements by adding
a ``_register(...)`` call in the relevant module — no other code needs to change.
"""

from . import accompaniment, progressions, rhythms, riffs, scales  # noqa: F401
