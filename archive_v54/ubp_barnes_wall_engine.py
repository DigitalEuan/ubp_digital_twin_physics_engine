"""
================================================================================
UBP BARNES-WALL ENGINE — v5.4 SHIM (DEPRECATED STANDALONE)
================================================================================
This file is a thin backwards-compatibility shim. The canonical
BarnesWallEngine is now part of the v5.4 backbone (ubp_unified_v5.py) and
is exposed through ubp_engine_substrate.

WHY THIS SHIM EXISTS
--------------------
Phase 3 of the v5.4 migration discovered that this standalone file was
orphaned — nothing in the digital twin actually imported it. The v5.4
backbone ships a cleaner BarnesWallEngine with:
  • Dependency-injected GolayCodeEngine in the constructor
  • Float-free Fraction arithmetic throughout
  • A rich audit() method returning dim/micro_nrci/macro_nrci/noisy_nrci/
    relative_coherence/clarity/decoder_gain/seed_hw/vector_hw/vector_norm_sq
  • nrci() + calculate_nrci alias

The original v1.6 standalone (Moire Interference theory, |u|u+v|
construction) is preserved at:
    archive_v53/ubp_barnes_wall_engine_v1_6_standalone.py

USAGE GOING FORWARD
-------------------
Prefer importing from ubp_engine_substrate:

    from ubp_engine_substrate import get_barnes_wall, BW_ENGINE
    bw = get_barnes_wall(256)              # fresh 256D instance
    bw_default = BW_ENGINE                 # global 256D singleton

Or directly from the backbone:

    from ubp_unified_v5 import BarnesWallEngine, BW_ENGINE
    bw = BarnesWallEngine(golay, dimension=256)   # explicit golay injection

This shim will be removed in a future phase once any external consumers
have migrated. New physics modules MUST NOT import from this file.

Author: E R A Craig, New Zealand (shim added July 2026, Phase 3 of v5.4 migration)
================================================================================
"""

# Re-export the v5.4-canonical BarnesWallEngine so any legacy imports still work.
from ubp_unified_v5 import BarnesWallEngine, BW_ENGINE, GOLAY_ENGINE

# v1.6 standalone exposed a generate()/snap()/audit_macro_state() API.
# v5.4 exposes generate()/snap()/audit() — same generate/snap, renamed audit.
# Provide a thin alias for backwards compatibility.
if not hasattr(BarnesWallEngine, 'audit_macro_state'):
    BarnesWallEngine.audit_macro_state = BarnesWallEngine.audit

# v1.6 also exposed a `macro_nrci` method (renamed to `nrci` in v5.4).
if not hasattr(BarnesWallEngine, 'macro_nrci'):
    BarnesWallEngine.macro_nrci = BarnesWallEngine.nrci

__all__ = ['BarnesWallEngine', 'BW_ENGINE', 'GOLAY_ENGINE']

# Deprecation notice (printed once per process, on import)
import warnings as _warnings
_warnings.warn(
    "ubp_barnes_wall_engine is a deprecated shim. Import BarnesWallEngine "
    "from ubp_engine_substrate (preferred) or ubp_unified_v5 instead. "
    "This shim will be removed in a future phase.",
    DeprecationWarning,
    stacklevel=2,
)
