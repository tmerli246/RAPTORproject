"""Algorithmic claims about the linear relaxation.

T2  incremental-efficiency greedy after dominance removal attains the LP optimum
T3  the integer optimum is below the LP optimum by at most the straddling gap
T4  the shadow price equals the derivative of the LP optimum with respect to
    capacity

The LP optimum is computed independently with scipy so that T2 is not checking
the greedy against itself.
"""

import numpy as np
import pytest
from scipy.optimize import linprog

from tps5d.core.schema import Facility
from tps5d.allocator.solve import solve_exact, solve_lp, solve_greedy
from tps5d.allocator.dominance import hull

from synth import Villaroel_cohort, ladder_cohort

def lp_reference(cohort, facility):
    """LP optimum of the full relaxation, without dominance removal."""
    opts, cols = cohort.by_patient(), []
    for pid in cohort.pids:
        cols += [(pid, s) for s in opts[pid]]

    c = [-cohort.dntcp(s) for _, s in cols]
    a_ub = [[s.occupancy for _, s in cols]]
    b_ub = [facility.budget]
    a_eq = [[1.0 if p == pid else 0.0 for p, _ in cols] for pid in cohort.pids]
    b_eq = [1.0] * len(cohort.pids)

    res = linprog(c, A_ub = a_ub, b_ub = b_ub, A_eq = a_eq, b_eq = b_eq, bounds = (0, 1))
    assert res.success
    return -res.fun

COHORTS = [
    ('reference', lambda: Villaroel_cohort(14, extra = 9.3), Facility(480.0)),
    ('concave', lambda: ladder_cohort(8, shape = 'concave'), Facility(480.0, days = 14)),
    ('linear', lambda: ladder_cohort(8, shape = 'linear'), Facility(480.0, days = 14)),
    ('convex', lambda: ladder_cohort(8, shape = 'convex'), Facility(480.0, days = 14)),
]

@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_t2_greedy_attains_lp_optimum(name, make, fac):
    cohort = make()
    lp = solve_lp(cohort, fac)
    assert lp.value == pytest.approx(lp_reference(cohort, fac), rel = 1e-9, abs = 1e-12)

@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_t3_integrality_gap(name, make, fac):
    cohort = make()
    lp = solve_lp(cohort, fac)
    ex = solve_exact(cohort, fac)
    total = sum(cohort.dntcp(s) for s in ex.choice.values())

    assert total <= lp.value + 1e-9

    # The gap is bounded by the utility of the single fractional upgrade, which
    # is a within-patient difference and not a whole patient's utility.
    if lp.frac is None:
        assert total == pytest.approx(lp.value, abs = 1e-9)
    else:
        pid, sid, w = lp.frac
        chain = [s for s in cohort.by_patient()[pid] if s.sid in lp.kept[pid]]
        step = max(cohort.dntcp(b) - cohort.dntcp(a)
                   for a, b in zip(chain, chain[1:]))
        assert lp.value - total <= step + 1e-9

@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_t4_shadow_price_is_the_derivative(name, make, fac):
    cohort = make()
    lp = solve_lp(cohort, fac)
    if lp.frac is None:
        assert lp.lam == 0.0          # capacity not binding
        return

    h = 1.0
    up = solve_lp(cohort, Facility(fac.cap_min_day + h / fac.days, fac.days))
    assert (up.value - lp.value) / h == pytest.approx(lp.lam, rel = 1e-6)

@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_greedy_is_feasible_and_below_exact(name, make, fac):
    cohort = make()
    gr = solve_greedy(cohort, fac)
    ex = solve_exact(cohort, fac)
    assert gr.used <= fac.budget + 1e-9
    assert gr.mean_dntcp <= ex.mean_dntcp + 1e-9

def test_hull_drops_interior_points():
    """A point below the segment joining its neighbours is removed."""
    pts = [(0.0, 0.0), (10.0, 0.4), (20.0, 1.0)]      # 0.4 < 0.5, below the line
    assert hull(pts) == [0, 2]

def test_hull_drops_collinear_points():
    pts = [(0.0, 0.0), (10.0, 0.5), (20.0, 1.0)]
    assert hull(pts) == [0, 2]

def test_hull_drops_dominated_and_equal_cost():
    """More expensive and no better, or same cost and worse, both go."""
    pts = [(0.0, 0.0), (10.0, 0.5), (10.0, 0.2), (15.0, 0.4), (20.0, 1.0)]
    assert hull(pts) == [0, 4]

def test_hull_keeps_a_concave_chain():
    pts = [(0.0, 0.0), (10.0, 0.6), (20.0, 1.0), (30.0, 1.2)]
    assert hull(pts) == [0, 1, 2, 3]