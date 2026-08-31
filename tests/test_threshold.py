"""The step-ratio threshold under a rationed photon budget (derivation note).

The closed form: dtau* (w) = tau0 * a / (m - w), valid for w < m, where w is the
photon outside-option value at the prevailing photon price. The whole effect of
the photon budget on the proton chain passes through w.

At version 6 the chain holds two rungs, PT-NA and PT-A, rather than a ladder of
adaptation counts. The block count B and the concavity exponent p entered the
version 5 form only through the factor B^(1-p), and both drop out: with no
intermediate counts there is no spacing for them to describe. What survives is
the version 4 form, and the geometry it describes is now a single step rather
than the first of several.

Checks, following Section 8 of the note:
1  the empirically located threshold matches the closed form across w
2  the threshold is monotone along the sweep
3  in the regime w >= m, PT-NA leaves the hull
4  w computed from the closed form at the solver's lambda_xt reproduces the
   solver's own photon choice per patient
"""

import numpy as np
import pytest

from tps5d.core.schema import Strategy, Cohort, Facility
from tps5d.allocator.dominance import hull
from tps5d.allocator.solve import solve_lp

N_FX, TAU0 = 30, 34.2
M, A, X = 0.069, 0.038, 0.030
DTAU_XT = 16.0

def w_of(lam_xt, x = X):
    """Photon outside-option value at the photon price.

    One adapted photon rung, so the maximum over rungs of version 5 collapses
    to a single term, floored at zero by the free non-adapted arm.
    """
    return max(0.0, x - lam_xt * N_FX * DTAU_XT)

def dtau_star(w):
    return TAU0 * A / (M - w)

def entry_survives(dtau_pt, w):
    """PT-NA on the hull of the proton chain augmented with the outside
    option (0, w)."""
    pts = [(0.0, w),
           (N_FX * TAU0, M),
           (N_FX * (TAU0 + dtau_pt), M + A)]
    return 1 in hull(pts)

def empirical_threshold(w, lo = 0.01, hi = 500.0):
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if entry_survives(mid, w):
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)

def test_closed_form_matches_the_hull_and_is_monotone():
    prev = -np.inf
    for lam in [1e9, 5e-5, 3e-5, 2e-5, 1e-5, 0.0]:
        w = w_of(lam)
        if w >= M:
            continue
        emp = empirical_threshold(w)
        assert emp == pytest.approx(dtau_star(w), rel = 1e-6)
        assert emp >= prev - 1e-9
        prev = emp

def test_endpoints_recover_the_version_4_forms():
    assert dtau_star(0.0) == pytest.approx(TAU0 * A / M)
    assert dtau_star(X) == pytest.approx(TAU0 * A / (M - X))

def test_regime_w_above_m_removes_pt_na():
    """A photon outside option worth more than the modality step removes
    non-adapted protons from the hull at any proton adaptation time."""
    w = 0.09                                    # > M
    assert w >= M
    for dtau_pt in [5.0, 20.0, 60.0, 200.0]:
        assert not entry_survives(dtau_pt, w)

def test_w_at_the_solver_price_reproduces_the_solver_photon_choice():
    """Coupling check: the reduction of the photon chain to the scalar w is
    exact, so the closed form at the solver's lambda_xt must reproduce whether
    each non-proton patient adapts. Patients within tie tolerance are skipped,
    since the LP may return either rung."""
    rng = np.random.default_rng(3)
    base, out = 0.30, []
    x_p = rng.uniform(0.01, 0.05, 10)
    m_p = rng.uniform(0.03, 0.09, 10)
    for i in range(10):
        pid = f"p{i:02d}"
        out.append(Strategy(pid, 'xt0', 'xt', N_FX, tau_pt = 0.0,
                            ntcp = {'tot': base}, baseline = True))
        out.append(Strategy(pid, 'xt1', 'xt', N_FX, tau_pt = 0.0,
                            tau_xt = DTAU_XT,
                            ntcp = {'tot': base - x_p[i]}, adapted = True))
        out.append(Strategy(pid, 'pt0', 'pt', N_FX, tau_pt = TAU0,
                            ntcp = {'tot': base - m_p[i]}))
        out.append(Strategy(pid, 'pt1', 'pt', N_FX, tau_pt = TAU0 + 12.0,
                            ntcp = {'tot': base - m_p[i] - A}, adapted = True))
    cohort = Cohort(out)

    fac = Facility(3.0 * N_FX * TAU0 / 12, 25.0, days = 12)
    lp = solve_lp(cohort, fac)

    frac_pids = {pid for pid, _, _ in lp.frac}
    for pid, s in lp.choice.items():
        if s.modality != 'xt' or pid in frac_pids:
            continue
        # Value of the adapted photon rung against the free one, at the
        # prevailing photon price. Its sign is what the solver should follow.
        gain = x_p[int(pid[1:])] - lp.lam_xt * N_FX * DTAU_XT
        if abs(gain) < 1e-9:
            continue
        assert s.adapted == (gain > 0.0), pid
