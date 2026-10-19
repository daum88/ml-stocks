"""Verdict generator — Tier A/B/C criteria and the D10 selection rule (spec §10.3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from trendbot.common.config import PreRegConfig


@dataclass
class VariantOutcome:
    name: str
    cagr: float
    calmar: float
    round_trips: int
    calmar_rank: float            # C4 percentile rank (0..1)
    cagr_rank: float
    sensitivity_calmars: List[float] = field(default_factory=list)
    criteria: Dict[str, bool] = field(default_factory=dict)
    tier: str = "C"


@dataclass
class Baselines:
    bh_cagr: float
    bh_calmar: Optional[float]
    exposure_matched_cagr: float


def evaluate_variant(name: str, cagr: float, calmar: float | None, round_trips: int,
                     calmar_rank: float, cagr_rank: float, sensitivity_calmars: list[float],
                     base: Baselines, cfg: PreRegConfig, window_years: float) -> VariantOutcome:
    cr = cfg.criteria
    vo = VariantOutcome(name=name, cagr=cagr, calmar=calmar if calmar is not None else 0.0,
                        round_trips=round_trips, calmar_rank=calmar_rank, cagr_rank=cagr_rank,
                        sensitivity_calmars=sensitivity_calmars)

    c = vo.criteria
    # C1 — absolute return floor.
    if base.bh_cagr > 0:
        c["C1"] = cagr > 0 and cagr >= cr.C1_return_floor_pct_of_bh * base.bh_cagr
    else:
        c["C1"] = cagr >= base.bh_cagr
    # C2 — exposure-matched floor.
    c["C2"] = cagr >= base.exposure_matched_cagr - cr.C2_exposure_match_penalty_pp
    # C3 — Calmar vs buy-and-hold.
    if base.bh_calmar is not None and base.bh_calmar > 0:
        c["C3"] = (calmar is not None) and (calmar >= cr.C3_calmar_mult_of_bh * base.bh_calmar)
    else:
        c["C3"] = (calmar is not None) and (base.bh_calmar is None or calmar > base.bh_calmar)
    # C4 — circular-shift percentile rank.
    c["C4"] = calmar_rank >= cr.C4_baseline_percentile
    # C5 — sanity floor (scaled by window length).
    floor = cr.C5_sanity_floor_trips[name] * (window_years / 8.0)
    c["C5"] = round_trips >= floor
    # C6 — robustness (each sensitivity variant beats B&H Calmar).
    if sensitivity_calmars:
        c["C6"] = all(s > (base.bh_calmar if base.bh_calmar is not None else 0.0)
                      for s in sensitivity_calmars)
    else:
        c["C6"] = True

    if all(c.values()):
        vo.tier = "A"
    elif c.get("C3") and c.get("C4") and c.get("C5") and not (c.get("C1") and c.get("C2")):
        vo.tier = "B"
    else:
        vo.tier = "C"
    return vo


def select(outcomes: dict[str, VariantOutcome], cfg: PreRegConfig) -> str:
    """Apply D10. Returns a human-readable selection sentence."""
    sel = cfg.criteria.selection
    v1 = outcomes.get("V1")
    v2 = outcomes.get("V2")
    v3 = outcomes.get("V3")

    if v1 is not None and v1.tier == "A":
        # V1 default; a faster variant replaces it only if Tier A AND beats on both by the margin.
        candidates = []
        for v in (v2, v3):
            if v is not None and v.tier == "A":
                if (v.cagr >= sel.replace_margin_cagr * v1.cagr
                        and v.calmar >= sel.replace_margin_calmar * v1.calmar):
                    candidates.append(v)
        if not candidates:
            return "live variant = V1"
        # higher Calmar; tie -> lower frequency (V2 = 4h is lower frequency than V3 = 1h)
        candidates.sort(key=lambda v: (-v.calmar, 0 if v.name == "V2" else 1))
        return f"live variant = {candidates[0].name}"

    # V1 not Tier A: no default; V2/V3 each need Tier A on their own.
    tier_a = [v for v in (v2, v3) if v is not None and v.tier == "A"]
    if not tier_a:
        # Any Tier B?
        if any(v is not None and v.tier == "B" for v in (v1, v2, v3)):
            return "Tier B only — human decision"
        return "Tier C — stop trading-bot track"
    tier_a.sort(key=lambda v: (-v.calmar, 0 if v.name == "V2" else 1))
    return f"live variant = {tier_a[0].name} (V1 not Tier A)"
