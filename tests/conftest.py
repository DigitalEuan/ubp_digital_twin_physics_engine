"""
Pytest configuration and shared fixtures for the UBP Digital Twin v5.4 migration.

Every test module imports the live ubp_unified_v5 backbone through this conftest,
so we have ONE place to swap the backbone during the migration.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── Path setup ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Toggle for GLM-gated tests (default off; flipped on once GLM is wired in)
os.environ.setdefault("UBP_GLM_ENABLED", "0")


# ── Shared fixtures ─────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def backbone():
    """Return the loaded ubp_unified_v5 module (session-cached)."""
    import ubp_unified_v5 as bb
    return bb


@pytest.fixture(scope="session")
def pp(backbone):
    """Return a session-cached UBPSourceCodeParticlePhysics instance."""
    return backbone.UBPSourceCodeParticlePhysics()


@pytest.fixture(scope="session")
def golay(backbone):
    return backbone.GolayCodeEngine()


@pytest.fixture(scope="session")
def leech(backbone, golay):
    return backbone.LeechLatticeEngine(golay)


@pytest.fixture(scope="session")
def monster(backbone):
    return backbone.MonsterGroup()


@pytest.fixture(scope="session")
def barnes_wall(backbone):
    return backbone.BarnesWallEngine(256)


@pytest.fixture(scope="session")
def triad(backbone, golay, leech):
    return backbone.TriadActivationEngine(golay, leech)


@pytest.fixture(scope="session")
def substrate(backbone):
    """Engine substrate — initially returns the v5.4 module until we wire
    ubp_engine_substrate back in during Phase 2."""
    return backbone


# ── GLM skip helper ────────────────────────────────────────────────────────
def glm_enabled() -> bool:
    return os.environ.get("UBP_GLM_ENABLED", "0") == "1"


skip_if_glm_disabled = pytest.mark.skipif(
    not glm_enabled(),
    reason="GLM is disabled (set UBP_GLM_ENABLED=1 to enable)",
)
