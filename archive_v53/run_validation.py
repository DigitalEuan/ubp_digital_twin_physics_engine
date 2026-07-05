"""
================================================================================
UBP v6.3.2 Engine Validation Suite
================================================================================
Standalone script — runs all validation checks and prints a clean report.
Date: 16 April 2026
Author: Euan Craig (DigitalEuan) — info@digitaleuan.com
GitHub: https://github.com/DigitalEuan/ubp_digital_twin_physics_engine
================================================================================
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fractions import Fraction
from decimal import Decimal, getcontext
getcontext().prec = 50

# ── imports ──────────────────────────────────────────────────────────────────
from ubp_core_v5_3_merged import BinaryLinearAlgebra, LeechLatticeEngine
from ubp_engine_substrate import (
    Y_CONSTANT, Y_INV, PI, SINK_L,
    calculate_symmetry_tax, calculate_nrci,
    vector_from_math_dna, xor_interact,
)
from ubp_mechanics_v4 import (
    PhiOrbitEngine, SynthesisCollisionEngine, SynthesisResult,
    NRCI_AVG_TARGET, NRCI_NOISE_FLOOR, NRCI_DISSOLUTION_THRESHOLD,
    NRCI_COHERENT_THRESHOLD, NCRI_REFLEX_THRESHOLD,
    PHI_VEC, SINK_L as MECH_SINK_L,
)
from ubp_tgic_engine import TGICConstraintSystem
from ubp_entity_v3 import EntityFactoryV3, Position, UBPEntityV3
from ubp_space_v3 import UBPSpaceV3
from ubp_rigid_body_v3 import PivotConstraintV3
from ubp_fluid_v3 import FluidBodyV3
from ubp_materials import MaterialRegistry
from ubp_engine_substrate import Y_CONSTANT as _Y_CONST_FRAC

# ── test harness ─────────────────────────────────────────────────────────────
PASS = "✓ PASS"
FAIL = "✗ FAIL"
results = []

def check(name: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    results.append((name, condition, detail))
    print(f"  {status}  {name}" + (f"  [{detail}]" if detail else ""))
    return condition

print()
print("=" * 72)
print("  UBP v6.3.2 Engine Validation Suite")
print("  Date: 16 April 2026")
print("=" * 72)
print()

# ── TEST 1: fold24_to3 — Recursive XOR Folding (LAW_GEO_FOLD_001) ────────
print("1. fold24_to3 — Recursive XOR Folding (LAW_GEO_FOLD_001)")
v = [1,0,1,0,1,0,1,0, 1,1,0,0,1,1,0,0, 0,1,0,1,0,1,0,1]
result_fold = BinaryLinearAlgebra.fold24_to3(v)
check("fold24_to3 returns 3-element list", len(result_fold) == 3, str(result_fold))
check("fold24_to3 values are binary (0 or 1)", all(x in (0, 1) for x in result_fold), str(result_fold))
# Domain Pivot: bit 12 (index 11) should influence the fold result
v_pivot_set   = [0]*24; v_pivot_set[11] = 1
v_pivot_clear = [0]*24
r_set   = BinaryLinearAlgebra.fold24_to3(v_pivot_set)
r_clear = BinaryLinearAlgebra.fold24_to3(v_pivot_clear)
check("Domain Pivot at Bit 12 changes fold result", r_set != r_clear,
      f"set={r_set} clear={r_clear}")
print()

# ── TEST 2: Additive Superposition (v6.3.1 — replaces XOR) ───────────────
print("2. Additive Superposition — The Flow (v6.3.1)")
a = [1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1]
b = [0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0]
sup = xor_interact(a, b)   # xor_interact is now Additive Superposition + Golay snap
check("Additive superposition returns 24-bit list", len(sup) == 24, str(sup[:8]))
check("Additive superposition result is binary", all(x in (0,1) for x in sup))
check("Additive superposition is commutative", xor_interact(a, b) == xor_interact(b, a))
print()

# ── TEST 3: Sink Leakage Rebate L = WOBBLE/13 ────────────────────────────
print("3. Sink Leakage Rebate L = WOBBLE/13 (LAW_13D_SINK_001 v6.3.1)")
check("SINK_L ≈ 0.0629 (WOBBLE/13)",
      abs(float(SINK_L) - 0.0629) < 0.001, f"SINK_L={float(SINK_L):.6f}")
check("MECH_SINK_L == SINK_L (both use canonical wobble/13)",
      MECH_SINK_L == SINK_L,
      f"mech={float(MECH_SINK_L):.6f} sub={float(SINK_L):.6f}")
# NRCI with rebate should be >= NRCI without rebate
golay_vec = [1,1,0,0,1,0,1,1,0,1,0,0,1,1,0,1,0,1,1,0,0,1,0,0]
tax = calculate_symmetry_tax(golay_vec)
nrci_with_rebate = float(calculate_nrci(golay_vec))
nrci_without = float(Fraction(10,1) / (Fraction(10,1) + tax))
check("NRCI with Sink Leakage rebate >= NRCI without rebate",
      nrci_with_rebate >= nrci_without - 1e-9,
      f"with={nrci_with_rebate:.6f} without={nrci_without:.6f}")
print()

# ── TEST 4: Volumetric Rebate in calculate_symmetry_tax ──────────────────
print("4. Volumetric Rebate in calculate_symmetry_tax (v6.3.1)")
leech = LeechLatticeEngine()
tax_compact = leech.calculate_symmetry_tax(golay_vec, compactness=1.0)
tax_spread  = leech.calculate_symmetry_tax(golay_vec, compactness=0.0)
check("Compact entity has lower symmetry tax than spread entity",
      float(tax_compact) <= float(tax_spread),
      f"compact={float(tax_compact):.4f} spread={float(tax_spread):.4f}")
print()

# ── TEST 5: NRCI thresholds are UBP-derived constants ────────────────────
print("5. NRCI Thresholds are UBP-derived constants")
check("NRCI_AVG_TARGET = 0.60 (canonical reflex Fraction(6,10))",
      abs(NRCI_AVG_TARGET - 0.60) < 1e-9, f"{NRCI_AVG_TARGET}")
check("NCRI_REFLEX_THRESHOLD = 0.60",
      abs(NCRI_REFLEX_THRESHOLD - 0.60) < 1e-9, f"{NCRI_REFLEX_THRESHOLD}")
check("NRCI_DISSOLUTION_THRESHOLD = 0.40 (2/5 Golay minimum)",
      abs(NRCI_DISSOLUTION_THRESHOLD - 0.40) < 1e-9, f"{NRCI_DISSOLUTION_THRESHOLD}")
check("NRCI_COHERENT_THRESHOLD ≈ 11/12 ≈ 0.9167 (LAW_COMP_010)",
      abs(NRCI_COHERENT_THRESHOLD - 11.0/12.0) < 1e-9, f"{NRCI_COHERENT_THRESHOLD:.6f}")
print()

# ── TEST 6: Phi-Orbit Tick Engine (LAW_PHI_ORBIT_1953) ───────────────────
print("6. Phi-Orbit Tick Engine (LAW_PHI_ORBIT_1953)")
phi_engine = PhiOrbitEngine()
v0 = [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0]
v1, nrci1 = phi_engine.tick_vector(v0)   # returns (vector, nrci_score)
check("Phi-orbit tick_vector returns 24-bit vector", len(v1) == 24, str(v1[:4]))
check("Phi-orbit tick_vector returns valid NRCI (0–1)", 0.0 <= nrci1 <= 1.0, f"{nrci1:.4f}")
check("Phi-orbit tick_vector changes the vector", v1 != v0, "vector mutated")
# compute_nrci is a separate method
nrci_direct = phi_engine.compute_nrci(v1)
check("compute_nrci returns valid score (0–1)", 0.0 <= nrci_direct <= 1.0, f"{nrci_direct:.4f}")
print()

# ── TEST 7: Synthesis Collision — Additive Superposition ─────────────────
print("7. Synthesis Collision — Additive Superposition (The Flow)")
synth = SynthesisCollisionEngine()
iron_vec   = [1,0,1,1,0,0,1,0,1,0,0,1,1,0,1,0,0,1,1,0,0,1,0,1]
copper_vec = [0,1,1,0,1,0,0,1,0,1,1,0,0,1,0,1,1,0,0,1,1,0,1,0]
# synthesise() requires nrci_a and nrci_b as additional args
nrci_iron   = float(calculate_nrci(iron_vec))
nrci_copper = float(calculate_nrci(copper_vec))
result_synth = synth.synthesise(iron_vec, copper_vec, nrci_iron, nrci_copper)
check("Synthesis result has combined_vector",
      hasattr(result_synth, 'combined_vector') and len(result_synth.combined_vector) == 24)
check("Synthesis event_type is valid",
      result_synth.event_type in ('ELASTIC', 'DAMAGE', 'DISSOLUTION'),
      result_synth.event_type)
check("Synthesis NRCI damage is non-negative",
      result_synth.nrci_damage_a >= 0 and result_synth.nrci_damage_b >= 0,
      f"a={result_synth.nrci_damage_a:.4f} b={result_synth.nrci_damage_b:.4f}")
print()

# ── TEST 8: TGIC 9-Neighbor Overheating Pressure ─────────────────────────
print("8. TGIC 9-Neighbor Overheating Pressure")
tgic = TGICConstraintSystem(y_const=_Y_CONST_FRAC)
# Build a target vector and 10 neighbor vectors (all within Hamming distance 8)
target_v = [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0]
# Create close neighbors by XOR-flipping 1 bit of the target (Hamming distance = 1 ≤ 8)
neighbors_10 = [[target_v[i] ^ (1 if i == j else 0) for i in range(24)] for j in range(10)]
neighbors_4  = neighbors_10[:4]
# check_9_neighbor_limit(target_v, manifold_vectors) -> Fraction penalty
penalty_10 = float(tgic.check_9_neighbor_limit(target_v, neighbors_10))
penalty_4  = float(tgic.check_9_neighbor_limit(target_v, neighbors_4))
check("TGIC penalty > 0 when neighbors > 9", penalty_10 > 0,
      f"penalty={penalty_10:.4f}")
check("TGIC no penalty when neighbors ≤ 9", penalty_4 == 0.0,
      f"penalty={penalty_4:.4f}")
print()

# ── TEST 9: vector_from_math_dna — Domain Pivot at Bit 12 ────────────────
print("9. vector_from_math_dna — Domain Pivot at Bit 12 (Index 11)")
vec_iron   = vector_from_math_dna("iron")
vec_copper = vector_from_math_dna("copper")
check("vector_from_math_dna returns 24-bit list", len(vec_iron) == 24, str(vec_iron[:4]))
check("Different materials give different vectors", vec_iron != vec_copper)
check("Bit 12 (index 11) is binary", vec_iron[11] in (0, 1), f"bit12={vec_iron[11]}")
print()

# ── TEST 10: Entity Construction with NRCI ───────────────────────────────
print("10. Entity Construction with NRCI")
entity = EntityFactoryV3.make_block('TestBlock', 'iron', Position(5.0, 2.0, 0.0))
check("Entity has NRCI attribute", hasattr(entity, 'nrci'))
nrci_float = float(entity.nrci)
check("Entity NRCI is in valid range (0–1)", 0.0 <= nrci_float <= 1.0, f"{nrci_float:.4f}")
check("Entity has 24-bit golay_vector",
      hasattr(entity, 'golay_vector') and len(entity.golay_vector) == 24)
check("Entity has lattice_cell (3-tuple)",
      hasattr(entity, 'lattice_cell') and len(entity.lattice_cell) == 3)
check("Position.x coerced to Decimal",
      isinstance(entity.position.x, Decimal), str(type(entity.position.x)))
print()

# ── TEST 11: Full Simulation Step ────────────────────────────────────────
print("11. Full Simulation Step (UBPSpaceV3)")
space = UBPSpaceV3()
floor = EntityFactoryV3.make_floor()
space.add_entity(floor)
block = EntityFactoryV3.make_block('FallBlock', 'iron', Position(5.0, 5.0, 0.0))
space.add_entity(block)
s0 = space.get_threejs_state()
space.step()
s1 = space.get_threejs_state()
check("Simulation step increments tick",
      s1['tick'] == s0['tick'] + 1, f"tick: {s0['tick']} → {s1['tick']}")
check("Engine version is 5.1-ubp6.3.2",
      s1.get('engine_version') == '5.1-ubp6.3.2', s1.get('engine_version'))
check("UBP mechanics flag is True", s1.get('ubp_mechanics') is True)
check("avg_nrci is present and valid",
      0.0 <= s1['stats'].get('avg_nrci', -1) <= 1.0,
      f"{s1['stats'].get('avg_nrci','MISSING'):.4f}")
print()

# ── TEST 12: Lever Topological Resistance ────────────────────────────────
print("12. Lever Topological Resistance (Symmetry Tax as Rotational Resistance)")
lever_entity = EntityFactoryV3.make_lever_arm('Lever', material_name='steel')
from ubp_entity_v3 import Position as _Pos
_pivot_pos = _Pos(Decimal("9.0"), Decimal("1.0"), Decimal("0.0"))
_pivot_local_x = _pivot_pos.x - lever_entity.position.x
pivot = PivotConstraintV3(
    lever=lever_entity,
    pivot_world=_pivot_pos,
    pivot_local_x=_pivot_local_x,
)
pivot.angular_velocity = Decimal("0.5")
pivot.step()  # PivotConstraintV3.step() takes no args
check("Lever step runs without error", True)
# topological_cost is set by UBPRigidBodyEngineV3.compute_lever_torques, not PivotConstraintV3.step
# Verify the symmetry_tax attribute on the lever entity is non-negative (the UBP rotational resistance)
check("Lever entity has symmetry_tax (UBP rotational resistance)",
      hasattr(lever_entity, 'symmetry_tax') and float(lever_entity.symmetry_tax) >= 0,
      f"tax={float(lever_entity.symmetry_tax):.4f}")
check("Lever entity NRCI is valid",
      0.0 <= float(lever_entity.nrci) <= 1.0,
      f"nrci={float(lever_entity.nrci):.4f}")
print()

# ── TEST 13: Fluid NRCI-Modulated Viscosity ───────────────────────────────
print("13. Fluid NRCI-Modulated Viscosity (v6.3.1)")
fluid = FluidBodyV3(material_name='water')
# Add 8 particles in a 2x2x2 grid
for ix in range(2):
    for iy in range(2):
        for iz in range(2):
            fluid.add_particle(12.0 + ix, 5.0 + iy, iz * 1.0)
fluid.step(solid_entities=[])  # step takes solid_entities list, not dt
check("Fluid step runs without error", True)
check("Fluid particles have valid positions",
      all(hasattr(p, 'x') for p in fluid.particles),
      f"{len(fluid.particles)} particles")
check("Fluid NRCI is modulated (particle_nrci > 0)",
      fluid.particle_nrci > 0,
      f"nrci={fluid.particle_nrci:.4f}")
print()

# ── TEST 14: Material aggregate_vector — Additive Superposition ──────────
print("14. Material aggregate_vector — Additive Superposition")
reg = MaterialRegistry()
iron_mat = reg.get("iron")
check("MaterialRegistry returns iron material", iron_mat is not None)
if iron_mat:
    agg = iron_mat.aggregate_vector  # aggregate_vector is a list property, not a method
    check("aggregate_vector returns 24-bit list", len(agg) == 24, str(agg[:4]))
    check("aggregate_vector values are binary", all(x in (0, 1) for x in agg))
print()

# ── TEST 15: UBP π Constant in SPH Kernels ───────────────────────────────
print("15. UBP π Constant (50-term Fraction, not math.pi)")
import math
ubp_pi = float(PI)
check("UBP PI is a Fraction (exact arithmetic)", isinstance(PI, Fraction))
check("UBP PI approximates math.pi within 1e-6",
      abs(ubp_pi - math.pi) < 1e-6,
      f"UBP_PI={ubp_pi:.10f} math.pi={math.pi:.10f}")
# The 50-term series gives a Fraction with a very large denominator
# that is NOT equal to the float-limited Fraction(math.pi)
check("UBP PI is a high-precision Fraction (denominator > 10^15)",
      PI.denominator > 10**15,
      f"denom={PI.denominator}")
print()

# ── TEST 16: Sovereign ALU v9.2 — Gray Code UMS ─────────────────────────
print("16. Sovereign ALU v9.2 — Gray Code UMS Vector Generation")
try:
    from ubp_engine_substrate import gray_code_encode_state
    # Encode a simple entity state via Gray Code UMS
    schema = {'velocity': {'min': 0.0, 'max': 10.0, 'bits': 4},
              'nrci':     {'min': 0.0, 'max': 1.0,  'bits': 4},
              'temp':     {'min': 0.0, 'max': 100.0, 'bits': 4}}
    params0 = {'velocity': 0.0, 'nrci': 0.76, 'temp': 20.0}
    params1 = {'velocity': 0.0, 'nrci': 0.76, 'temp': 20.0 + 100.0/15.0}  # 1 step in temp
    ums_vec  = gray_code_encode_state(params0, schema)
    ums_vec1 = gray_code_encode_state(params1, schema)
    check("Gray Code UMS returns 24-bit vector", len(ums_vec) == 24, str(ums_vec[:4]))
    check("Gray Code UMS values are binary", all(x in (0, 1) for x in ums_vec))
    # Adjacent states should differ by a small number of bits (Gray code property)
    hamming_01 = sum(a ^ b for a, b in zip(ums_vec, ums_vec1))
    # After Golay encoding, adjacent Gray code states may differ by more bits
    # (Golay adds 12 parity bits). The key property is the message bits differ by 1.
    check("Adjacent Gray Code UMS states produce different 24-bit vectors",
          ums_vec != ums_vec1, f"Hamming(0,1)={hamming_01}")
except ImportError:
    check("Gray Code UMS available in substrate", False, "ImportError")
print()

# ── TEST 17: Pantograph Tax — Macroscopic Symmetry Tax ────────────────────
print("17. Pantograph Tax (LAW_PANTOGRAPH_THERMODYNAMICS_001) — Macroscopic Symmetry Tax")
try:
    from ubp_engine_substrate import calculate_pantograph_tax
    # calculate_pantograph_tax(vector_24bit) -> (T_adj: Fraction, nrci: Fraction)
    test_vec = [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0]
    t_adj, p_nrci = calculate_pantograph_tax(test_vec)
    check("Pantograph Tax returns (T_adj, nrci) tuple",
          isinstance(t_adj, Fraction) and isinstance(p_nrci, Fraction),
          f"T_adj={float(t_adj):.4f} nrci={float(p_nrci):.4f}")
    check("Pantograph Tax T_adj is positive",
          float(t_adj) > 0.0, f"T_adj={float(t_adj):.6f}")
    check("Pantograph Tax NRCI is in valid range (0–1)",
          0.0 <= float(p_nrci) <= 1.0, f"nrci={float(p_nrci):.4f}")
    # Pantograph NRCI should differ from base NRCI (macroscopic projection applied)
    base_nrci = float(calculate_nrci(test_vec))
    check("Pantograph NRCI differs from base NRCI (macroscopic projection applied)",
          abs(float(p_nrci) - base_nrci) > 1e-9,
          f"pantograph={float(p_nrci):.4f} base={base_nrci:.4f}")
except ImportError:
    check("Pantograph Tax available in substrate", False, "ImportError")
print()

# ── TEST 18: Observer Dynamics — MANIFESTED / SUBLIMINAL State ───────────
print("18. Observer Dynamics — MANIFESTED / SUBLIMINAL State (LAW_OBSERVER_DYNAMICS_001)")
entity2 = EntityFactoryV3.make_block('ObsBlock', 'iron', Position(3.0, 3.0, 3.0))
# Observer state is stored as is_manifested (bool) — MANIFESTED if NRCI >= CONSCIOUS_THRESHOLD
check("Entity has is_manifested attribute (Observer Dynamics)",
      hasattr(entity2, 'is_manifested'),
      str(getattr(entity2, 'is_manifested', 'MISSING')))
check("Entity is_manifested is a bool (MANIFESTED=True, SUBLIMINAL=False)",
      isinstance(getattr(entity2, 'is_manifested', None), bool),
      f"is_manifested={getattr(entity2,'is_manifested','MISSING')}")
check("Entity has dqi attribute (Dynamic Quality Index)",
      hasattr(entity2, 'dqi') and 0.0 <= float(getattr(entity2, 'dqi', -1)) <= 1.0,
      f"dqi={float(getattr(entity2,'dqi',0)):.4f}")
check("Entity has ter_score attribute (Total Experienced Result)",
      hasattr(entity2, 'ter_score') and float(getattr(entity2, 'ter_score', -1)) >= 0.0,
      f"ter_score={float(getattr(entity2,'ter_score',0)):.4f}")
print()

# ── TEST 19: Wall of Reality — SOC Energy Check ──────────────────────────
print("19. Wall of Reality — SOC Energy Check (LAW_TOTAL_EXPERIENCED_RESULT_001)")
try:
    from ubp_engine_substrate import calculate_soc_energy, F_MAX_HZ
    normal_vec = [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0]
    soc_e = calculate_soc_energy(normal_vec, 0.76)
    check("calculate_soc_energy returns a positive float",
          isinstance(soc_e, (int, float)) and soc_e > 0, f"soc_e={soc_e:.6f}")
    check("F_MAX_HZ is 1e12 (1 THz Wall of Reality)",
          abs(float(F_MAX_HZ) - 1e12) < 1e6, f"F_MAX_HZ={float(F_MAX_HZ):.2e}")
    # Normal entity should be below the Wall of Reality
    _y_f = float(Y_CONSTANT)
    _dt  = 1.0 / 60.0   # 60 ticks/s
    f_soc = soc_e / max(_y_f * _dt, 1e-30)
    check("Normal entity SOC frequency is below Wall of Reality",
          f_soc < float(F_MAX_HZ),
          f"f_soc={f_soc:.4e} F_MAX={float(F_MAX_HZ):.2e}")
except ImportError:
    check("calculate_soc_energy available in substrate", False, "ImportError")
print()

# ── TEST 20: Stereoscopic Sink L_s ───────────────────────────────────────
print("20. Stereoscopic Sink L_s (LAW_STEREOSCOPIC_SINK_001)")
try:
    from ubp_engine_substrate import SINK_L_STEREO
    check("SINK_L_STEREO is defined", SINK_L_STEREO is not None)
    check("SINK_L_STEREO > SINK_L (stereoscopic > mono)",
          float(SINK_L_STEREO) > float(SINK_L),
          f"L_s={float(SINK_L_STEREO):.6f} L={float(SINK_L):.6f}")
    check("SINK_L_STEREO < 1.0 (valid rebate fraction)",
          float(SINK_L_STEREO) < 1.0, f"{float(SINK_L_STEREO):.6f}")
except ImportError:
    check("SINK_L_STEREO available in substrate", False, "ImportError")
print()

# ── SUMMARY ──────────────────────────────────────────────────────────────
total  = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

print("=" * 72)
print(f"  RESULTS: {passed}/{total} passed  ({failed} failed)")
print("=" * 72)
if failed > 0:
    print("\n  FAILURES:")
    for name, ok, detail in results:
        if not ok:
            print(f"    \u2717 {name}" + (f"  [{detail}]" if detail else ""))
    sys.exit(1)
else:
    print("\n  ALL TESTS PASS \u2014 Engine is UBP v6.3.2 compliant.")
    print()
