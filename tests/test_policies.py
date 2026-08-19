"""Properties the policy comparison must satisfy.

P3 is an upper bound on every other policy by construction. Nothing else is
ordered a priori: whether P2b beats P2a on a given cohort is the empirical
question the comparison exists to answer.

The cohorts include both single-resource ones, guarding the version 4
behaviour, and two-chain ones exercising the photon budget rule.
"""

import pytest

from tps5d.core.schema import Facility
from tps5d.allocator.policies import POLICIES, compare

from synth import villarroel_cohort, ladder_cohort

COHORTS = [
    ('reference', lambda: villarroel_cohort(14, extra = 9.3), Facility(480.0)),
    ('concave', lambda: ladder_cohort(8, shape = 'concave'), Facility(480.0, days = 12)),
    ('linear', lambda: ladder_cohort(8, shape = 'linear'), Facility(480.0, days = 12)),
    ('convex', lambda: ladder_cohort(8, shape = 'convex'), Facility(480.0, days = 12)),
    ('two-chain', lambda: ladder_cohort(8, x_gain = 0.02, dtau_xt = 16.0),
     Facility(480.0, 40.0, days = 12)),
    ('two-chain tight', lambda: ladder_cohort(8, x_gain = 0.03, dtau_xt = 16.0),
     Facility(240.0, 10.0, days = 12)),
]

@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_all_policies_respect_both_budgets(name, make, fac):
    cohort = make()
    for pol, alloc in compare(cohort, fac).items():
        assert alloc.used_pt <= fac.budget_pt + 1e-9, pol
        assert alloc.used_xt <= fac.budget_xt + 1e-9, pol

@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_exact_bounds_every_policy(name, make, fac):
    cohort = make()
    res = compare(cohort, fac)
    for pol, alloc in res.items():
        assert alloc.mean_dntcp <= res['P3'].mean_dntcp + 1e-9, pol

@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_every_patient_receives_exactly_one_strategy(name, make, fac):
    cohort = make()
    for pol, alloc in compare(cohort, fac).items():
        assert set(alloc.choice) == set(cohort.pids), pol

@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_no_policy_harms_the_cohort(name, make, fac):
    """Every policy can fall back on the baseline, so the mean cannot go negative."""
    cohort = make()
    for pol, alloc in compare(cohort, fac).items():
        assert alloc.mean_dntcp >= -1e-12, pol

def test_p0_uses_no_adaptation():
    cohort = ladder_cohort(8)
    alloc = POLICIES['P0'](cohort, Facility(480.0, days = 12))
    assert all(s.n_adapt == 0 for s in alloc.choice.values())

def test_p1_adapts_every_proton_patient():
    cohort = ladder_cohort(8, n_block = 2)
    alloc = POLICIES['P1'](cohort, Facility(480.0, days = 12))
    pt = [s for s in alloc.choice.values() if s.modality == 'pt']
    assert pt and all(s.n_adapt == 2 for s in pt)

def test_p1_spends_no_photon_budget():
    """P1 is the reference-study world: the adapted photon arm does not exist
    there, however large the budget."""
    cohort = ladder_cohort(8, x_gain = 0.02, dtau_xt = 16.0)
    alloc = POLICIES['P1'](cohort, Facility(240.0, 1e6, days = 12))
    assert alloc.used_xt == 0.0

def test_p1x_reduces_to_p1_at_zero_photon_budget():
    cohort = ladder_cohort(8, x_gain = 0.02, dtau_xt = 16.0)
    fac = Facility(240.0, 0.0, days = 12)
    a1 = POLICIES['P1'](cohort, fac)
    a1x = POLICIES['P1x'](cohort, fac)
    assert {p: s.sid for p, s in a1.choice.items()} == \
           {p: s.sid for p, s in a1x.choice.items()}

def test_p1x_adapts_displaced_patients_in_benefit_order():
    """With budget for exactly one full photon adaptation, the displaced
    patient with the largest photon benefit receives it."""
    cohort = ladder_cohort(8, x_gain = 0.02, dtau_xt = 16.0, n_fx = 30)
    fac_pt = Facility(240.0, days = 12)
    a1 = POLICIES['P1'](cohort, fac_pt)
    displaced = [p for p, s in a1.choice.items() if s.modality == 'xt']
    assert displaced, "test needs displaced patients; tighten the proton budget"

    best_xta = {p: max((cohort.dntcp(s)
                        for s in cohort.by_patient()[p] if s.occ_xt > 0),
                       default = 0.0) for p in displaced}
    top = max(best_xta, key = best_xta.get)

    one = 30 * 16.0                              # one fully adapted course
    a1x = POLICIES['P1x'](cohort, Facility(240.0, one / 12, days = 12))
    assert a1x.choice[top].modality == 'xt' and a1x.choice[top].n_adapt > 0
