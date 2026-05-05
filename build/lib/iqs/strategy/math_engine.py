from __future__ import annotations

# Backward-compatible import: keep implementation centralized.
# NOTE: Once stable, move the full implementation here and delete `iqs/math_engine.py`.
import iqs.math_engine as _me

# Re-export everything that callers may expect.
from iqs.math_engine import *  # noqa: F403

# Ensure key hot-path symbols are available even if not in __all__.
hotpath_vwap_bands_signal = _me.hotpath_vwap_bands_signal

