"""Algorithmic claims introduced by the second resource.

T7   each multiplier equals the finite difference of the LP optimum with
     respect to its own budget, holding the other fixed
T8   at C_XT = 0 the two-resource solve reproduces the version 4
     single-resource result exactly
T9   beyond the cohort's photon adaptation demand, lambda_xt is zero and
     every patient not receiving protons holds an adapted photon option
T15  swapping the roles of the two resources reproduces the mirrored problem

T8 and T9 are the endpoints of the normalised C_XT sweep and double as
regression tests: the version 4 behaviour must survive as a boundary case
rather than be replaced.

Registered as T15, not T10, in allocator design 5.4: T10 there is the no-harm
claim tested in test_admissibility.py, unconnected to this one. The two
shared the label only here, never in the design document itself.
"""

import numpy as np
import pytest

from tps5d.core.schema import Facility, Strategy, Cohort
from tps5d.allocator.solve import solve_exact, solve_lp, solve_dp, solve_lp_greedy

from tps5d.generator.synth import arm_cohort

def two_chain(n = 8, seed = 0, **kw):
    kw.setdefault('x_gain', 0.02)
    kw.setdefault('dtau_xt', 16.0)
    return arm_cohort(n, seed = seed, **kw)

FACS = [
    ('interior', Facility(240.0, 30.0, days = 12)),
    ('tight photon', Facility(240.0, 5.0, days = 12)),
    ('loose proton', Facility(480.0, 30.0, days = 12)),
]

@pytest.mark.parametrize('name, fac', FACS)
def test_t7_each_dual_is_its_own_finite_difference(name, fac):
    cohort = two_chain()
    lp = solve_lp(cohort, fac)
    h = 1.0

    up_pt = solve_lp(cohort, Facility(fac.cap_pt_min_day + h / fac.days,
                                      fac.cap_xt_min_day, fac.days))
    assert (up_pt.value - lp.value) / h == pytest.approx(lp.lam_pt,
                                                         rel = 1e-6, abs = 1e-12)

    up_xt = solve_lp(cohort, Facility(fac.cap_pt_min_day,
                                      fac.cap_xt_min_day + h / fac.days, fac.days))
    assert (up_xt.value - lp.value) / h == pytest.approx(lp.lam_xt,
                                                         rel = 1e-6, abs = 1e-12)

def test_t8_zero_photon_budget_reproduces_version_4_exactly():
    """The ILP at C_XT = 0 equals the retained dynamic program on the
    single-resource restriction, in value and in proton patient set, and the
    LP duals equal the greedy break efficiency."""
    cohort = two_chain()
    fac = Facility(240.0, 0.0, days = 12)

    ilp = solve_exact(cohort, fac)
    dp = solve_dp(cohort.restrict(lambda s: s.tau_xt == 0.0),
                  Facility(240.0, days = 12))

    assert ilp.used_xt == 0.0
    assert ilp.mean_dntcp == pytest.approx(dp.mean_dntcp, abs = 1e-12)
    assert {p for p, s in ilp.choice.items() if s.modality == 'pt'} == \
           {p for p, s in dp.choice.items() if s.modality == 'pt'}

    lp = solve_lp(cohort, fac)
    gr = solve_lp_greedy(cohort, Facility(240.0, days = 12))
    assert lp.value == pytest.approx(gr.value, rel = 1e-9)
    assert lp.lam_pt == pytest.approx(gr.lam_pt, rel = 1e-6, abs = 1e-12)

def test_t9_saturated_photon_budget():
    """Beyond cohort demand the photon constraint cannot bind: lambda_xt is
    zero, and every non-proton patient holds an adapted photon option, since
    the synthetic photon benefit is strictly positive."""
    cohort = two_chain()
    demand = cohort.demand_xt()
    fac = Facility(240.0, 2.0 * demand / 12, days = 12)

    lp = solve_lp(cohort, fac)
    assert lp.lam_xt == pytest.approx(0.0, abs = 1e-12)

    ex = solve_exact(cohort, fac)
    for s in ex.choice.values():
        if s.modality == 'xt':
            assert s.adapted

def test_t15_swapping_the_resources_mirrors_the_problem():
    """Relabel every strategy's costs onto the other axis and swap the budgets:
    the optimal value must be unchanged. Guards axis indexing in the model."""
    cohort = two_chain(n = 6)
    fac = Facility(240.0, 20.0, days = 12)

    def flip(s):
        modality = 'xt' if s.modality == 'pt' else 'pt'
        return Strategy(s.pid, s.sid, modality, s.n_fx,
                        tau_pt = s.tau_xt, tau_xt = s.tau_pt,
                        ntcp = dict(s.ntcp), scheme = s.scheme,
                        adapted = s.adapted, baseline = s.baseline)

    mirrored = Cohort([flip(s) for s in cohort.strategies])
    swapped = Facility(fac.cap_xt_min_day, fac.cap_pt_min_day, fac.days)

    a = solve_exact(cohort, fac)
    b = solve_exact(mirrored, swapped)
    assert a.mean_dntcp == pytest.approx(b.mean_dntcp, abs = 1e-12)

    lp_a = solve_lp(cohort, fac)
    lp_b = solve_lp(mirrored, swapped)
    assert lp_a.value == pytest.approx(lp_b.value, abs = 1e-12)
    assert lp_a.lam_pt == pytest.approx(lp_b.lam_xt, rel = 1e-9, abs = 1e-12)
    assert lp_a.lam_xt == pytest.approx(lp_b.lam_pt, rel = 1e-9, abs = 1e-12)
