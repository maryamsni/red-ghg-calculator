"""
GHG calculator for renewable fuel supply chains following EU RED II, Annex V, Part C.

    E = e_ec + e_l + e_p + e_td + e_u - e_sca - e_ccs - e_ccr      [g CO2e per MJ fuel]
    Savings = (EF - E) / EF                                         EF = fossil fuel comparator (94 g/MJ)

The pathway is described in three simple files:
    <pathway>_steps.csv       - every input per supply-chain step (amount per fuel output) and its RED term
    <pathway>_settings.json   - fuel output, heating values, co-products, installation start date
    emission_factors_fuels.csv - emission factor per input

Run:  python red_ghg.py
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
TERMS = ["eec", "el", "ep", "etd", "eu", "esca", "eccs", "eccr"]
CREDITS = {"esca", "eccs", "eccr"}          # savings terms are subtracted


# ---------- 1. Load the pathway ----------

def load_pathway(name="uco_biodiesel"):
    steps = pd.read_csv(HERE / f"{name}_steps.csv")
    settings = json.loads((HERE / f"{name}_settings.json").read_text())
    factors = pd.read_csv(HERE / "emission_factors_fuels.csv").set_index("input")["factor"].to_dict()
    return steps, settings, factors


# ---------- 2. Co-product allocation (RED II Annex V, C.17) ----------

def allocation_factor(settings):
    """Share of emissions carried by the fuel, by energy content (lower heating value)."""
    fuel_energy = settings["fuel_output_kg"] * settings["fuel_lhv_mj_per_kg"]
    coproduct_energy = sum(c["output_kg"] * c["lhv_mj_per_kg"] for c in settings.get("coproducts", []))
    return fuel_energy / (fuel_energy + coproduct_energy)


# ---------- 3. Calculate ----------

def calculate(steps, settings, factors, overrides=None):
    """Return a table of emissions per input in g CO2e per MJ of fuel."""
    factors = {**factors, **(overrides or {})}
    missing = sorted(set(steps["input"]) - set(factors))
    if missing:
        raise ValueError(f"No emission factor for: {', '.join(missing)}. Add them to emission_factors_fuels.csv.")
    unknown = sorted(set(steps["term"]) - set(TERMS))
    if unknown:
        raise ValueError(f"Unknown RED term(s): {', '.join(unknown)}. Use one of {TERMS}.")

    alloc = allocation_factor(settings)
    fuel_mj = settings["fuel_output_kg"] * settings["fuel_lhv_mj_per_kg"]

    rows = steps.copy()
    rows["kg_co2e"] = rows["amount"] * rows["input"].map(factors)
    # emissions up to the step that produces the co-product are shared with it
    rows["allocated"] = rows["before_coproduct"].str.lower().eq("yes")
    rows.loc[rows["allocated"], "kg_co2e"] *= alloc
    rows["g_per_mj"] = rows["kg_co2e"] * 1000 / fuel_mj
    rows.loc[rows["term"].isin(CREDITS), "g_per_mj"] *= -1
    return rows


def summarise(rows, settings):
    E = rows["g_per_mj"].sum()
    ef = settings["fossil_comparator_g_per_mj"]
    savings = (ef - E) / ef
    threshold = savings_threshold(settings["installation_start"])
    return {"E_g_per_mj": E, "savings": savings, "threshold": threshold, "compliant": savings >= threshold,
            "by_term": rows.groupby("term")["g_per_mj"].sum().reindex(TERMS, fill_value=0.0)}


def savings_threshold(start):
    """Minimum GHG savings for transport biofuels by installation start date (RED II Art. 29(10))."""
    d = date.fromisoformat(start)
    if d <= date(2015, 10, 5):
        return 0.50
    if d <= date(2020, 12, 31):
        return 0.60
    return 0.65


# ---------- 4. Report ----------

def hotspot_chart(rows, settings, path):
    by_input = (rows.assign(label=rows["step"] + ": " + rows["input"])
                .groupby("label")["g_per_mj"].sum().sort_values())
    ax = by_input.plot(kind="barh", color="#2E7D5B", figsize=(8, 4))
    ax.set_xlabel("g CO2e per MJ fuel")
    ax.set_ylabel("")
    ax.set_title(f"Hotspots - {settings['pathway']}")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def print_result(title, res):
    print(f"\n{title}")
    print(f"  Carbon intensity E = {res['E_g_per_mj']:.2f} g CO2e/MJ")
    print(f"  GHG savings vs. fossil comparator = {res['savings']:.1%} "
          f"(threshold {res['threshold']:.0%}: {'OK' if res['compliant'] else 'NOT MET'})")


def main():
    steps, settings, factors = load_pathway()
    print(f"Pathway: {settings['pathway']}")
    print(f"Allocation factor fuel vs. co-products (energy basis): {allocation_factor(settings):.3f}")

    rows = calculate(steps, settings, factors)
    base = summarise(rows, settings)
    print_result("Base case", base)
    print("  By RED term (g CO2e/MJ):")
    for term, value in base["by_term"].items():
        if value:
            print(f"    {term:5s} {value:6.2f}")

    # Optimisation scenarios - the kind of CI-score levers a client asks about
    for title, overrides in [("Scenario: renewable electricity", {"electricity": 0.03}),
                             ("Scenario: bio-methanol instead of fossil methanol", {"methanol": 0.50}),
                             ("Scenario: both", {"electricity": 0.03, "methanol": 0.50})]:
        print_result(title, summarise(calculate(steps, settings, factors, overrides), settings))

    rows.round(4).to_csv(HERE / "results_uco_biodiesel.csv", index=False)
    hotspot_chart(rows, settings, HERE / "hotspots_uco_biodiesel.png")
    print("\nSaved results_uco_biodiesel.csv and hotspots_uco_biodiesel.png")


if __name__ == "__main__":
    main()
