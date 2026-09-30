"""Rules of the allocation policies that a change to the ranking or to the
budget accounting would break without any other test noticing.

Cohorts are built by hand, with the arithmetic in each docstring, or from
generator parameters whose effect is stated in the test.
"""

import pytest

from tps5d.core.schema import Strategy, Cohort, Facility
from tps5d.allocator.policies import POLICIES, spend_photon_budget
from tps5d.allocator.solve import solve_greedy, solve_lp
from tps5d.allocator.report import sweep

from tps5d.generator.synth import arm_cohort, two_scheme_cohort

BASE = 0.30


def st(pid, sid, modality, tau_pt = 0.0, tau_xt = 0.0, dntcp = 0.0, n_fx = 1, **kw):
    """One strategy with delta NTCP `dntcp` against the patient baseline."""
    return Strategy(pid, sid, modality, n_fx = n_fx, tau_pt = tau_pt,
                    tau_xt = tau_xt, ntcp = {'tot': BASE - dntcp}, **kw)

def xt0(pid, **kw):
    """The free reference arm."""
    return st(pid, 'xt', 'xt', baseline = True, **kw)

def rank_cohort(specs):
    """specs: [(pid, tau_pt, dntcp)], one proton option per patient."""
    out = []
    for pid, tau, d in specs:
        out += [xt0(pid), st(pid, 'pt', 'pt', tau_pt = tau, dntcp = d)]
    return Cohort(out)


# Photon budget rule (allocator 5.3)

def photon_default_cohort():
    """p01 has an inadmissible reference arm, so its default is xt1 (40 min of
    photon adaptation, committed before any policy runs). xt2 buys more for 60
    min in total, so 20 min incrementally."""
    return Cohort([
        xt0('p00'),
        st('p00', 'pt', 'pt', tau_pt = 30.0, dntcp = 0.10, n_fx = 10, adapted = True),
        xt0('p01', admissible = False, n_fx = 10),
        st('p01', 'xt1', 'xt', tau_xt = 4.0, dntcp = 0.01, n_fx = 10, adapted = True),
        st('p01', 'xt2', 'xt', tau_xt = 12.0, dntcp = 0.03, n_fx = 5,
           adapted = True, scheme = 'hyp'),
    ])

@pytest.mark.parametrize('budget, expected', [(50.0, 'xt1'), (59.9, 'xt1'), (60.0, 'xt2')])
def test_photon_upgrade_pays_only_the_increment_against_the_remaining_budget(budget, expected):
    """The default holds 40 min. The upgrade costs 20 more. A budget of 50 must
    refuse it (a rule that ignored committed minutes would spend 60), and 60
    must accept it exactly."""
    cohort = photon_default_cohort()
    choice = spend_photon_budget(cohort, dict(cohort.default()), budget)
    assert choice['p01'].sid == expected
    assert sum(s.occ_xt for s in choice.values()) <= budget + 1e-9

def test_photon_rule_ties_go_to_the_cheaper_option_whatever_the_list_order():
    """Two XT-A options of equal benefit, both affordable: the one with fewer
    minutes is taken, whichever comes first in the list."""
    def cohort(order):
        arms = {'a': st('p', 'a', 'xt', tau_xt = 8.0, dntcp = 0.05, n_fx = 10, adapted = True),
                'b': st('p', 'b', 'xt', tau_xt = 2.0, dntcp = 0.05, n_fx = 10, adapted = True,
                        scheme = 'hyp')}
        return Cohort([xt0('p')] + [arms[k] for k in order])
    for order in ('ab', 'ba'):
        c = cohort(order)
        assert spend_photon_budget(c, dict(c.default()), 200.0)['p'].sid == 'b'


# Referral and greedy ranking

def test_referral_order_is_decreasing_benefit():
    """One slot, three candidates: P0 and P1 refer the patient with the
    largest benefit."""
    cohort = rank_cohort([('p0', 30.0, 0.03), ('p1', 30.0, 0.09), ('p2', 30.0, 0.05)])
    for name in ('P0', 'P1'):
        alloc = POLICIES[name](cohort, Facility(30.0))
        assert {p for p, s in alloc.choice.items() if s.modality == 'pt'} == {'p1'}, name

def test_referral_does_not_refer_a_patient_with_no_benefit():
    """At the default threshold of zero, a proton option that buys nothing
    would consume machine minutes for no gain."""
    cohort = rank_cohort([('p0', 30.0, 0.0), ('p1', 30.0, 0.04)])
    alloc = POLICIES['P0'](cohort, Facility(1e3))
    assert {p for p, s in alloc.choice.items() if s.modality == 'pt'} == {'p1'}

def test_p2b_is_the_greedy_on_efficiency_and_is_strictly_below_the_optimum_here():
    """B: 10 min for 0.03 (0.0030/min). C: 55 min for 0.10 (0.0018/min).
    Budget 60. Greedy takes B, then C no longer fits: 0.03. Optimum takes C
    alone: 0.10. This pins P2b as the greedy (not exact, not ranked on
    absolute gain, which would also return 0.10)."""
    cohort = rank_cohort([('B', 10.0, 0.03), ('C', 55.0, 0.10)])
    fac = Facility(60.0)
    assert POLICIES['P2b'](cohort, fac).mean_dntcp == pytest.approx(0.03 / 2)
    assert solve_greedy(cohort, fac).mean_dntcp == pytest.approx(0.03 / 2)
    assert POLICIES['P3'](cohort, fac).mean_dntcp == pytest.approx(0.10 / 2)


# P1x holds the schedule fixed (Q2)

def test_p1x_uses_the_standard_schedule_only_so_it_is_flat_below_one_standard_course():
    """One standard-schedule adapted photon course costs n_std x dtau_xt = 480
    min; a hypofractionated one costs 80. Below 480 min P1x has nothing it may
    buy and equals P1, and it does not decrease as the budget grows. Left free to
    choose the schedule, P1x would already differ from P1 at 80 min."""
    make = lambda: two_scheme_cohort(n = 10, tau0 = 34.2, dtau = 25.7, shape = 'both_schemes',
                                     x_gain = 0.02, dtau_xt = 16.0, seed = 3)
    cohort, days, course = make(), 12, 480.0
    p1x_prev = None
    for courses in (0.0, 1 / 6, 1 / 2, 1.0, 2.0, 3.0):
        fac = Facility(855.0, courses * course / days, days = days)
        p1 = POLICIES['P1'](cohort, fac).mean_dntcp
        p1x = POLICIES['P1x'](cohort, fac).mean_dntcp
        if courses < 1.0:
            assert p1x == pytest.approx(p1, abs = 1e-12), courses
        if p1x_prev is not None:
            assert p1x >= p1x_prev - 1e-12, courses
        p1x_prev = p1x
    assert p1x > p1 + 1e-6          # three courses buy something at this load


# Reporting

def test_sweep_records_the_shadow_prices_of_the_solved_lp_not_swapped():
    """Both prices are non-zero and different here, so a swap or a constant
    zero cannot pass."""
    cohort = arm_cohort(8, x_gain = 0.02, dtau_xt = 16.0)
    fac = Facility(240.0, 30.0, days = 12)
    lp = solve_lp(cohort, fac)
    assert lp.lam_pt > 0.0 and lp.lam_xt > 0.0 and lp.lam_pt != pytest.approx(lp.lam_xt)
    recs = sweep(lambda dt: arm_cohort(8, dtau = dt, x_gain = 0.02, dtau_xt = 16.0),
                 fac, [10.0], POLICIES)
    for r in recs:
        assert r['lambda_pt'] == pytest.approx(lp.lam_pt)
        assert r['lambda_xt'] == pytest.approx(lp.lam_xt)
