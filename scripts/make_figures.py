"""Produce the allocator's figures and result tables from generated cohorts.

Run from the repository root, with the package importable:

    python scripts/make_figures.py [outdir]

Two files per figure (PDF and PNG) and two CSV files are written to `outdir`
(default `figures`).

Only the generation of cohorts (`make`, `SEEDS`) is synthetic. The drawing
functions of `tps5d.allocator.figures` take a list of result records, one per
cohort and point, so the same figures can be drawn from results on real cohorts
by replacing that section. Every figure carries the synthetic marker and every
CSV row carries `synthetic = True` while the cohorts come from the generator.
Whether a spread over real patients is drawn, and how it is obtained, is a
scientific decision that is not taken here.

Figures
    policy_curves       cohort delta NTCP against the proton adaptation time, at
                        zero photon budget (the T8 regime). P1x is P1 there and is
                        not drawn twice
    shadow_price        lambda_PT against the same axis
    cohort_composition  arms held under P3, same axis
    option_ladder       one named patient's proton option set, the two reductions
    budget_curves       lambda_PT and lambda_XT against C_XT / D_XT, at DTAU_BUDGET
    policy_budget       every policy against C_XT in standard courses, at DTAU_BUDGET
"""

import sys
from pathlib import Path

from tps5d.core.schema import Facility
from tps5d.allocator.policies import POLICIES, p1
from tps5d.allocator import figures as fg
from tps5d.allocator.report import sweep, sweep_budget_xt, to_csv, dominance_counts

from tps5d.generator.synth import two_scheme_cohort

# Reference study scenarios S1 to S6 (allocator 2).
DTAUS = [2.4, 5.7, 9.3, 13.7, 19.0, 25.7]
DTAU_REF = DTAUS[3]          # S4: the cohort of the option ladder
DTAU_BUDGET = max(DTAUS)     # proton adaptation time of the budget figures: the largest
                             # of the sweep, where most patients are displaced to photons

# Generated cohorts. Illustrative: none of these values is a measurement.
N_PATIENTS = 10
SEEDS = range(100)
TAU0 = 34.2                  # min per fraction, non-adapted session of the reference study
N_STD = 30                   # fractions, standard schedule
DTAU_XT = 16.0               # min per adapted photon fraction, McComas anchor (allocator 9.1);
                             # not a measurement, decision 12 is open
X_GAIN = 0.02                # scale of the photon adaptation benefit; illustrative, no source
PEN_XT = 0.0                 # penalty of the hypofractionated photon arm (generator); zero
                             # leaves it as good as the standard one

# 855 min x 12 days = 10260 min = N_PATIENTS x N_STD x TAU0: every patient fits on
# standard non-adapted protons, load 1.0 at zero adaptation time as in the
# reference study, so every displacement below is caused by adaptation time.
FACILITY = Facility(855.0, days = 12)

# One standard-schedule adapted photon course, per patient, in machine-minutes.
COURSE_MIN = N_STD * DTAU_XT

# Named patient of the option ladder.
LADDER_SEED, LADDER_PID = 3, 'p00'

NOTE = (f"n = {N_PATIENTS}, load 1.0, tau0 = {TAU0:g} min, "
        f"dtau_XT = {DTAU_XT:g} min")

def make(dtau, seed):
    """One generated cohort."""
    return two_scheme_cohort(n = N_PATIENTS, tau0 = TAU0, dtau = dtau, shape = 'both_schemes',
                             x_gain = X_GAIN, dtau_xt = DTAU_XT, pen_xt = PEN_XT, seed = seed)

def tag(records, seed):
    for r in records:
        r['cohort'] = seed
        r['synthetic'] = True
    return records

def courses_grid():
    """Photon budget grid in standard courses: 0, a hypofractionated course
    (1/6), 1/3, 1/2, one course, then whole courses up to the number of
    patients P1 leaves on photons at DTAU_BUDGET, the largest over the cohorts.
    Beyond that no policy has anyone left to adapt on photons."""
    n_photon = 0
    for seed in SEEDS:
        cohort = make(DTAU_BUDGET, seed)
        choice = p1(cohort, FACILITY).choice
        n_photon = max(n_photon, sum(1 for s in choice.values() if s.modality == 'xt'))
    return [0.0, 1 / 6, 1 / 3, 1 / 2] + [float(c) for c in range(1, n_photon + 1)]

def main(outdir = 'figures'):
    out = Path(outdir)
    out.mkdir(parents = True, exist_ok = True)
    fg.use_style()

    # Sweep over the proton adaptation time, at zero photon budget. Adaptation
    # time changes occupancy, so each cohort is rebuilt at each point.
    records = []
    for seed in SEEDS:
        records += tag(sweep(lambda dt, seed = seed: make(dt, seed), FACILITY, DTAUS, POLICIES), seed)
    to_csv(records, out / 'policy_sweep.csv')

    at_zero = [p for p in POLICIES if p != 'P1x']       # P1x is P1 at zero photon budget
    fg.policy_curves(records, out / 'fig_policy_curves.pdf', policies = at_zero,
                     note = NOTE + '; C_XT = 0, P1x = P1')
    fg.shadow_price(records, out / 'fig_shadow_price.pdf', note = NOTE + '; C_XT = 0')
    fg.cohort_composition(records, policy = 'P3', path = out / 'fig_cohort_composition.pdf',
                          note = NOTE + '; C_XT = 0')

    cohort = make(DTAU_REF, LADDER_SEED)
    fg.option_ladder(cohort, LADDER_PID, path = out / 'fig_option_ladder.pdf',
                     note = f"seed {LADDER_SEED}, dtau_PT = {DTAU_REF:g} min")

    # Sweep over the photon budget, at one proton adaptation time.
    courses = courses_grid()
    budget = []
    for seed in SEEDS:
        cohort = make(DTAU_BUDGET, seed)
        fracs = [c * COURSE_MIN / cohort.demand_xt() for c in courses]
        budget += tag(sweep_budget_xt(cohort, FACILITY, fracs, POLICIES), seed)
    to_csv(budget, out / 'budget_sweep.csv')

    note = NOTE + f'; dtau_PT = {DTAU_BUDGET:g} min'
    fg.budget_curves(budget, out / 'fig_budget_curves.pdf', note = note)
    fg.policy_budget(budget, COURSE_MIN, out / 'fig_policy_budget.pdf', note = note)

    per_patient, tot = dominance_counts(make(DTAU_REF, LADDER_SEED))
    print(f"{len(SEEDS)} cohorts of {N_PATIENTS} patients; budget grid, in courses: "
          f"{[round(c, 3) for c in courses]}")
    print(f"ladder cohort: options {tot['n_options']}, "
          f"Pareto dominated {tot['n_pareto']}, LP dominated {tot['n_lp']}")
    print(f"written to {out.resolve()}")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'figures')
