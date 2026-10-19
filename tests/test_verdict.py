"""Verdict logic tests with crafted metric sets (spec §11)."""
import pytest

from trendbot.report import verdict as V
from trendbot.report.verdict import Baselines


def _base(bh_cagr=0.20, bh_calmar=1.0, em=0.18):
    return Baselines(bh_cagr=bh_cagr, bh_calmar=bh_calmar, exposure_matched_cagr=em)


def test_tier_a_all_pass(prereg):
    b = _base()
    vo = V.evaluate_variant("V1", cagr=0.20, calmar=1.5, round_trips=20,
                            calmar_rank=0.99, cagr_rank=0.99, sensitivity_calmars=[1.2],
                            base=b, cfg=prereg, window_years=8.0)
    assert vo.tier == "A"
    assert all(vo.criteria.values())


def test_tier_b_return_conditions_fail(prereg):
    b = _base(bh_cagr=0.20, bh_calmar=1.0, em=0.18)
    # C1 and C2 fail (cagr too low); C3/C4/C5 pass.
    vo = V.evaluate_variant("V1", cagr=0.05, calmar=1.5, round_trips=20,
                            calmar_rank=0.99, cagr_rank=0.99, sensitivity_calmars=[1.2],
                            base=b, cfg=prereg, window_years=8.0)
    assert vo.tier == "B"
    assert vo.criteria["C1"] is False and vo.criteria["C2"] is False
    assert vo.criteria["C3"] is True


def test_tier_c_when_calmar_fails(prereg):
    b = _base(bh_cagr=0.20, bh_calmar=1.0, em=0.18)
    vo = V.evaluate_variant("V1", cagr=0.20, calmar=0.5, round_trips=20,
                            calmar_rank=0.99, cagr_rank=0.99, sensitivity_calmars=[1.2],
                            base=b, cfg=prereg, window_years=8.0)
    assert vo.tier == "C"
    assert vo.criteria["C3"] is False


def test_c1_uses_absolute_floor_when_bh_negative(prereg):
    b = _base(bh_cagr=-0.10, bh_calmar=-0.5, em=-0.10)
    vo = V.evaluate_variant("V1", cagr=-0.05, calmar=0.0, round_trips=20,
                            calmar_rank=0.99, cagr_rank=0.99, sensitivity_calmars=[0.0],
                            base=b, cfg=prereg, window_years=8.0)
    # C1: strategy CAGR >= B&H CAGR (-0.05 >= -0.10) -> True
    assert vo.criteria["C1"] is True


def test_c3_uses_strict_greater_when_bh_calmar_negative(prereg):
    b = _base(bh_cagr=0.10, bh_calmar=-0.5, em=0.10)
    vo = V.evaluate_variant("V1", cagr=0.10, calmar=0.0, round_trips=20,
                            calmar_rank=0.99, cagr_rank=0.99, sensitivity_calmars=[0.0],
                            base=b, cfg=prereg, window_years=8.0)
    assert vo.criteria["C3"] is True  # 0.0 > -0.5


def test_c4_exact_threshold(prereg):
    b = _base()
    vo = V.evaluate_variant("V1", cagr=0.20, calmar=1.5, round_trips=20,
                            calmar_rank=0.95, cagr_rank=0.95, sensitivity_calmars=[1.2],
                            base=b, cfg=prereg, window_years=8.0)
    assert vo.criteria["C4"] is True  # >= 95%


def test_selection_v1_default_when_faster_does_not_beat(prereg):
    o = {
        "V1": V.VariantOutcome(name="V1", cagr=0.20, calmar=1.0, round_trips=10, calmar_rank=0.99, cagr_rank=0.99, tier="A"),
        "V2": V.VariantOutcome(name="V2", cagr=0.22, calmar=1.1, round_trips=30, calmar_rank=0.99, cagr_rank=0.99, tier="A"),
        "V3": V.VariantOutcome(name="V3", cagr=0.10, calmar=0.5, round_trips=80, calmar_rank=0.99, cagr_rank=0.99, tier="C"),
    }
    # V2 beats V1 by 10% not 20% -> no replacement.
    assert V.select(o, prereg) == "live variant = V1"


def test_selection_v2_replaces_v1_on_both_margins(prereg):
    o = {
        "V1": V.VariantOutcome(name="V1", cagr=0.10, calmar=0.5, round_trips=10, calmar_rank=0.99, cagr_rank=0.99, tier="A"),
        "V2": V.VariantOutcome(name="V2", cagr=0.13, calmar=0.65, round_trips=30, calmar_rank=0.99, cagr_rank=0.99, tier="A"),
        "V3": V.VariantOutcome(name="V3", cagr=0.05, calmar=0.2, round_trips=80, calmar_rank=0.99, cagr_rank=0.99, tier="C"),
    }
    # V2 = 1.3x V1 CAGR and 1.3x V1 Calmar -> replaces.
    assert V.select(o, prereg) == "live variant = V2"


def test_selection_tier_c_when_none_pass(prereg):
    o = {
        "V1": V.VariantOutcome(name="V1", cagr=0.0, calmar=0.0, round_trips=0, calmar_rank=0.0, cagr_rank=0.0, tier="C"),
        "V2": V.VariantOutcome(name="V2", cagr=0.0, calmar=0.0, round_trips=0, calmar_rank=0.0, cagr_rank=0.0, tier="C"),
        "V3": V.VariantOutcome(name="V3", cagr=0.0, calmar=0.0, round_trips=0, calmar_rank=0.0, cagr_rank=0.0, tier="C"),
    }
    assert "Tier C" in V.select(o, prereg)


def test_selection_v1_not_a_pick_higher_calmar(prereg):
    o = {
        "V1": V.VariantOutcome(name="V1", cagr=0.0, calmar=0.0, round_trips=0, calmar_rank=0.0, cagr_rank=0.0, tier="C"),
        "V2": V.VariantOutcome(name="V2", cagr=0.10, calmar=0.8, round_trips=30, calmar_rank=0.99, cagr_rank=0.99, tier="A"),
        "V3": V.VariantOutcome(name="V3", cagr=0.10, calmar=1.2, round_trips=80, calmar_rank=0.99, cagr_rank=0.99, tier="A"),
    }
    # V3 has higher Calmar -> picked.
    assert V.select(o, prereg) == "live variant = V3 (V1 not Tier A)"
