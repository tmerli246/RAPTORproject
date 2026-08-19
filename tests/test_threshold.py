"""The step-ratio threshold under a rationed photon budget (derivation note).

The closed form: dtau* (w) = tau0 * a * B^(1-p) / (m - w), valid for w < m,
where w is the photon outside-option value at the prevailing photon price. The
whole effect of the photon budget on the proton ladder passes through w.

Checks, following Section 8 of the note:
1  the empirically located threshold matches the closed form across w
2  the threshold is monotone along the sweep
3  in the regime w >= m, PT-NA leaves the hull
4  w computed from the closed form at the solver's lambda_xt reproduces the
   solver's own photon choice per patient

At p = 1 the adaptation increments are collinear and the hull removes them as
alternative optima, so survival means the entry rung PT-NA on the hull; genuine
survival of intermediate adapted rungs additionally requires p < 1.
"""

import numpy as np
import pytest

from tps5d.core.schema import Strategy, Cohort, Facility
from tps5d.allocator.dominance import hull
from tps5d.allocator.solve import solve_lp

B, N_FX, TAU0 = 2, 30, 34.2
M, A, X = 0.069, 0.038, 0.030
DTAU_XT = 16.0

def w_of(lam_xt, x = X, q = 1.0):
    """Photon outside-option value at the photon price."""
    return max(0.0, max(x * (j / B) ** q - lam_xt * j * (N_FX / B) * DTAU_XT
                        for j in range(1, B + 1)))

def dtau_star(w, p = 1.0):
    return TAU0 * A * B ** (1 - p) / (M - w)

def entry_survives(dtau_pt, w, p = 1.0):
    """PT-NA on the hull of the proton chain augmented with the outside
    option (0, w)."""
    pts = [(0.0, w), (N_FX * TAU0, M)]
    pts += [(N_FX * TAU0 + k * (N_FX / B) * dtau_pt, M + A * (k / B) ** p)
            for k in range(1, B + 1)]
    return 1 in hull(pts)

def empirical_threshold(w, p = 1.0, lo = 0.01, hi = 500.0):
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if entry_survives(mid, w, p):
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)

@pytest.mark.parametrize('p', [1.0, 0.7])
def test_closed_form_matches_the_hull_and_is_monotone(p):
    prev = -np.inf
    for lam in [1e9, 5e-5, 3e-5, 2e-5, 1e-5, 0.0]:
        w = w_of(lam)
        if w >= M:
            continue
        emp = empirical_threshold(w, p)
        assert emp == pytest.approx(dtau_star(w, p), rel = 1e-6)
        assert emp >= prev - 1e-9
        prev = emp

def test_endpoints_recover_the_version_4_forms():
    assert dtau_star(0.0) == pytest.approx(TAU0 * (A / M) * B ** 0)
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
    exact, so the closed form at the solver's lambda_xt must reproduce which
    photon rung each non-proton patient holds. Patients within tie tolerance
    of two rungs are skipped, since the LP may return either."""
    rng = np.random.default_rng(3)
    base, out = 0.30, []
    x_p = rng.uniform(0.01, 0.05, 10)
    m_p = rng.uniform(0.03, 0.09, 10)
    for i in range(10):
        pid = f"p{i:02d}"
        out.append(Strategy(pid, 'xt0', 'xt', N_FX, tau_pt = 0.0,
                            ntcp = {'tot': base}, baseline = True))
        for j in range(1, B + 1):
            out.append(Strategy(pid, f'xt{j}', 'xt', N_FX, tau_pt = 0.0,
                                tau_xt = DTAU_XT * j / B,
                                ntcp = {'tot': base - x_p[i] * j / B},
                                n_adapt = j))
        for k in range(B + 1):
            out.append(Strategy(pid, f'pt{k}', 'pt', N_FX,
                                tau_pt = TAU0 + 12.0 * k / B,
                                ntcp = {'tot': base - m_p[i] - A * k / B},
                                n_adapt = k))
    cohort = Cohort(out)

    fac = Facility(3.0 * N_FX * TAU0 / 12, 25.0, days = 12)
    lp = solve_lp(cohort, fac)

    frac_pids = {pid for pid, _, _ in lp.frac}
    for pid, s in lp.choice.items():
        if s.modality != 'xt' or pid in frac_pids:
            continue
        vals = {j: x_p[int(pid[1:])] * j / B - lp.lam_xt * j * (N_FX / B) * DTAU_XT
                for j in range(B + 1)}
        best = max(vals.values())
        ties = [j for j, v in vals.items() if abs(v - best) < 1e-9]
        if len(ties) > 1:
            continue
        assert s.n_adapt == ties[0], pid
