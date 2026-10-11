"""Checks for the RED GHG calculator. Run: pytest"""

import pandas as pd
import pytest

from red_ghg import load_pathway, allocation_factor, calculate, summarise, savings_threshold


def test_allocation_by_energy_content():
    _, settings, _ = load_pathway()
    # 1000 kg x 37 MJ/kg fuel vs. 100 kg x 16 MJ/kg glycerine
    assert allocation_factor(settings) == pytest.approx(37000 / (37000 + 1600))


def test_distribution_after_coproduct_is_not_allocated():
    steps, settings, factors = load_pathway()
    rows = calculate(steps, settings, factors)
    dist = rows[rows["step"] == "Distribution"].iloc[0]
    assert dist["kg_co2e"] == pytest.approx(300 * 0.10)


def test_savings_formula():
    steps, settings, factors = load_pathway()
    res = summarise(calculate(steps, settings, factors), settings)
    assert res["savings"] == pytest.approx((94 - res["E_g_per_mj"]) / 94)


@pytest.mark.parametrize("start,expected", [("2014-01-01", 0.50), ("2018-06-01", 0.60), ("2023-01-01", 0.65)])
def test_thresholds_by_installation_date(start, expected):
    assert savings_threshold(start) == expected


def test_greener_inputs_lower_the_carbon_intensity():
    steps, settings, factors = load_pathway()
    base = summarise(calculate(steps, settings, factors), settings)["E_g_per_mj"]
    green = summarise(calculate(steps, settings, factors, {"electricity": 0.03}), settings)["E_g_per_mj"]
    assert green < base


def test_credit_terms_are_subtracted():
    steps, settings, factors = load_pathway()
    extra = pd.DataFrame([{"step": "CCS", "term": "eccs", "input": "truck", "amount": 100, "unit": "tkm",
                           "before_coproduct": "no", "comment": "test credit"}])
    base = summarise(calculate(steps, settings, factors), settings)["E_g_per_mj"]
    with_credit = summarise(calculate(pd.concat([steps, extra]), settings, factors), settings)["E_g_per_mj"]
    assert with_credit < base


def test_missing_factor_gives_clear_error():
    steps, settings, factors = load_pathway()
    extra = pd.DataFrame([{"step": "X", "term": "ep", "input": "unknown_chemical", "amount": 1, "unit": "kg",
                           "before_coproduct": "yes", "comment": ""}])
    with pytest.raises(ValueError, match="unknown_chemical"):
        calculate(pd.concat([steps, extra]), settings, factors)
