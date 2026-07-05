"""
================================================================================
UBP PHYSICS REGISTRY — Extension Point for Future Physics Modules
================================================================================
A lightweight plugin registry for adding new physics domains to the digital
twin without modifying the substrate or the engine substrate.

WHY THIS EXISTS
---------------
The user has flagged that the digital twin will grow to encompass many
additional physics domains (electromagnetism, thermodynamics beyond what's
in ubp_physics_v3, chemistry, biology, etc.). Rather than have each new
module import directly from ubp_engine_substrate and risk name collisions
or import-order issues, this registry provides a single, well-documented
extension point.

DESIGN
------
1. Each physics domain provides a `PhysicsDomain` instance with:
   - name (unique identifier, e.g. 'electromagnetism')
   - version (string, e.g. '0.1.0')
   - constants (dict of Fraction values, sourced from PARTICLE_PHYSICS)
   - engines (dict of name→engine instances)
   - formulas (dict of name→callable, each returns a Fraction prediction)
   - validate() method that returns a status dict
2. Domains register themselves at import time:
       from ubp_physics_registry import register_domain, PhysicsDomain
       register_domain(PhysicsDomain(name='electromagnetism', ...))
3. The substrate exposes the registry through:
       from ubp_engine_substrate import get_physics_registry
       registry = get_physics_registry()
       em = registry.get_domain('electromagnetism')
4. The validate_substrate() function automatically iterates registered
   domains and includes their validation results in the report.

This pattern is deliberately minimal — no metaclasses, no decorators, no
implicit behavior. Just a dict and a dataclass.

USAGE EXAMPLE — adding a new physics domain
-------------------------------------------
In a new file `ubp_electromagnetism.py`:

    from fractions import Fraction
    from ubp_physics_registry import PhysicsDomain, register_domain
    from ubp_engine_substrate import PARTICLE_PHYSICS, Y_CONSTANT, PI

    # Constants (sourced from substrate — single source of truth)
    EM_CONSTS = {
        'epsilon_0': Fraction(1) / (4 * PI * 299792458**2 * 10**-7),  # F/m
        'mu_0':      4 * PI * Fraction(10, 1) ** -7,                  # H/m
    }

    # Formulas (each returns a Fraction prediction)
    def coulomb_constant():
        \"\"\"k_e = 1/(4*pi*epsilon_0) ~= 8.988e9 N*m^2/C^2\"\"\"
        return Fraction(1) / (4 * PI * EM_CONSTS['epsilon_0'])

    EM_FORMULAS = {
        'coulomb_constant': coulomb_constant,
    }

    def em_validate():
        k = float(coulomb_constant())
        target = 8.9875517873681764e9
        err = abs(k - target) / target * 100
        return {
            'coulomb_constant': {
                'predicted': k, 'target': target, 'error_pct': err,
                'budget': 0.001,  # exact by construction
                'status': 'GREEN' if err < 0.001 else 'YELLOW',
            },
            'status': 'GREEN' if err < 0.001 else 'YELLOW',
        }

    register_domain(PhysicsDomain(
        name='electromagnetism',
        version='0.1.0',
        description='Coulomb, Maxwell, Lorentz — substrate-derived.',
        constants=EM_CONSTS,
        engines={},  # no domain-specific engines yet
        formulas=EM_FORMULAS,
        validate=em_validate,
    ))

Then in any consumer:

    from ubp_engine_substrate import get_physics_registry
    em = get_physics_registry().get_domain('electromagnetism')
    k_e = em.formulas['coulomb_constant']()   # → Fraction

Author: Phase 3 of v5.4 migration (July 2026)
================================================================================
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable, Dict, List, Optional


# ── Dataclass ──────────────────────────────────────────────────────────────
@dataclass
class PhysicsDomain:
    """A self-contained physics domain registered with the substrate.

    Attributes:
        name:        Unique identifier (e.g. 'electromagnetism').
        version:     Semver-style version string (e.g. '0.1.0').
        description: Human-readable summary.
        constants:   Dict of Fraction (or int) values. By convention these
                     should be sourced from PARTICLE_PHYSICS or derived from
                     substrate primitives — NOT empirical hardcodes.
        engines:     Dict of name → engine instance. May be empty.
        formulas:    Dict of name → callable returning a Fraction prediction.
        validate:    Optional callable returning a status dict (must include
                     a 'status' key with value 'GREEN', 'YELLOW', or 'RED').
        depends_on:  Optional list of other domain names that must be
                     registered before this one can be activated.
    """
    name: str
    version: str
    description: str = ""
    constants: Dict[str, Any] = field(default_factory=dict)
    engines: Dict[str, Any] = field(default_factory=dict)
    formulas: Dict[str, Callable[[], Fraction]] = field(default_factory=dict)
    validate: Optional[Callable[[], Dict[str, Any]]] = None
    depends_on: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.name:
            raise ValueError("PhysicsDomain.name must be a non-empty string")
        if not self.version:
            raise ValueError(f"PhysicsDomain {self.name!r}: version is required")

    def formula_value(self, name: str) -> Fraction:
        """Compute and return the named formula's predicted value."""
        if name not in self.formulas:
            raise KeyError(f"Domain {self.name!r} has no formula {name!r}")
        return self.formulas[name]()


# ── Registry (thread-safe singleton) ───────────────────────────────────────
class _PhysicsRegistry:
    """Thread-safe registry of physics domains.

    Implemented as a class-level singleton — there is exactly one registry
    per Python process. Domains register themselves at import time.
    """

    _instance: Optional["_PhysicsRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "_PhysicsRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._domains = {}  # type: ignore[attr-defined]
                    cls._instance._order = []    # type: ignore[attr-defined]
        return cls._instance

    @property
    def domains(self) -> Dict[str, PhysicsDomain]:
        return dict(self._domains)

    @property
    def registered_names(self) -> List[str]:
        return list(self._order)

    def register(self, domain: PhysicsDomain, *, replace: bool = False) -> None:
        """Register a physics domain.

        Args:
            domain:  The PhysicsDomain to register.
            replace: If True, replace any existing domain with the same name.
                     If False (default), raise ValueError on collision.

        Raises:
            ValueError: if a domain with the same name exists and replace=False.
            ValueError: if any dependency in domain.depends_on is not registered.
        """
        if not isinstance(domain, PhysicsDomain):
            raise TypeError(f"Expected PhysicsDomain, got {type(domain).__name__}")

        # Check dependencies
        missing = [d for d in domain.depends_on if d not in self._domains]
        if missing:
            raise ValueError(
                f"Domain {domain.name!r} depends on unregistered domains: {missing}. "
                f"Register them first."
            )

        with self._lock:
            if domain.name in self._domains and not replace:
                existing = self._domains[domain.name]
                raise ValueError(
                    f"Domain {domain.name!r} already registered "
                    f"(existing version={existing.version}, new version={domain.version}). "
                    f"Pass replace=True to override."
                )
            if domain.name not in self._domains:
                self._order.append(domain.name)
            self._domains[domain.name] = domain

    def unregister(self, name: str) -> Optional[PhysicsDomain]:
        """Remove a domain from the registry. Returns the removed domain
        (or None if it wasn't registered)."""
        with self._lock:
            removed = self._domains.pop(name, None)
            if removed is not None and name in self._order:
                self._order.remove(name)
            return removed

    def get_domain(self, name: str) -> PhysicsDomain:
        """Retrieve a registered domain by name. Raises KeyError if missing."""
        if name not in self._domains:
            raise KeyError(
                f"No physics domain registered as {name!r}. "
                f"Registered: {self.registered_names}"
            )
        return self._domains[name]

    def has_domain(self, name: str) -> bool:
        return name in self._domains

    def validate_all(self) -> Dict[str, Any]:
        """Run every registered domain's validate() method and aggregate
        the results into a single report dict.

        Domains without a validate() method are skipped (status='SKIP').
        """
        results: Dict[str, Any] = {}
        for name in self._order:
            domain = self._domains[name]
            if domain.validate is None:
                results[name] = {
                    'status': 'SKIP',
                    'note': 'No validate() method defined',
                    'version': domain.version,
                }
                continue
            try:
                v = domain.validate()
                if not isinstance(v, dict) or 'status' not in v:
                    results[name] = {
                        'status': 'YELLOW',
                        'note': f"validate() returned malformed result: {v!r}",
                        'version': domain.version,
                    }
                else:
                    results[name] = v
            except Exception as e:
                results[name] = {
                    'status': 'RED',
                    'error': f"{type(e).__name__}: {e}",
                    'version': domain.version,
                }
        # Aggregate status
        statuses = [r.get('status', 'RED') for r in results.values()]
        if 'RED' in statuses:
            overall = 'RED'
        elif 'YELLOW' in statuses or 'SKIP' in statuses:
            overall = 'YELLOW'
        else:
            overall = 'GREEN'
        results['_overall'] = overall
        results['_domain_count'] = len(self._order)
        return results


# ── Public API ─────────────────────────────────────────────────────────────
def get_registry() -> _PhysicsRegistry:
    """Return the global physics registry singleton."""
    return _PhysicsRegistry()


def register_domain(domain: PhysicsDomain, *, replace: bool = False) -> None:
    """Register a physics domain with the global registry."""
    get_registry().register(domain, replace=replace)


def get_domain(name: str) -> PhysicsDomain:
    """Retrieve a registered domain by name."""
    return get_registry().get_domain(name)


def list_domains() -> List[str]:
    """Return the names of all registered domains in registration order."""
    return get_registry().registered_names


def validate_all_domains() -> Dict[str, Any]:
    """Validate every registered domain and return an aggregated report."""
    return get_registry().validate_all()


__all__ = [
    'PhysicsDomain',
    'get_registry',
    'register_domain',
    'get_domain',
    'list_domains',
    'validate_all_domains',
]
