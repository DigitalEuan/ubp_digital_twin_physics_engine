from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_closeout_docs_exist():
    assert (ROOT / 'FINAL_12_SLICE_ROADMAP.md').exists()
    assert (ROOT / 'MANUAL_ACCEPTANCE_CHECKLIST.md').exists()


def test_closeout_modules_exist():
    assert (ROOT / 'ubp_world_scenarios.py').exists()
    assert (ROOT / 'ubp_domain_effects.py').exists()
    assert (ROOT / 'ubp_reality_alignment.py').exists()
