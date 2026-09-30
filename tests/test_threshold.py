"""The step-ratio threshold under a rationed photon budget (derivation note).

The closed form: dtau* (w) = tau0 * a / (m - w), valid for w < m, where w is the
photon outside-option value at the prevailing photon price. The whole effect of
the photon budget on the proton chain passes through w.

Within one schedule the proton chain holds two rungs, PT-NA and PT-A, so the
geometry is a single step. The block count and any concavity exponent do not
enter: with no intermediate adaptation counts there is no spacing for them to
describe.

Checks, following Section 8 of the note:
1  the empirically located threshold matches the closed form across w
2  the threshold is monotone along the sweep
3  in the regime w >= m, PT-NA leaves the hull
4  w computed from the closed form at the solver's lambda_xt reproduces the
   solver's own photon choice per patient
5  T14 (allocator design 5.4). On a real cohort with heterogeneous (m_p, a_p,
   x_p), whether PT-NA survives the hull of its own proton chain augmented
   with (0, w_p), read via dominance.hull, agrees with the closed-form
   threshold evaluated at the solver's own lambda_xt, patient by patient

T14 is scoped to a single fractionation scheme by design, not as a
simplification pending later work. Road 1: "The threshold is a per-scheme
statement... That cross-scheme interaction is the subject of the study and is
resolved by the allocator, not by a closed form." Section 6.5 recovers the
reference study's own headline number in closed form; that is the distinct
claim T14 checks, and it is not meant to characterise the pooled two-scheme
proton frontier, which chains() and ladders() reduce without ever forming
the (0, w) point at all: P2a/P2b rank the proton chain against its own free
base (allocator design 5.3), never against the photon price. The (0, w)
augmentation is a property of the true LP optimum, not of the production
greedy path, so T14 checks the closed form against dominance.hull directly
rather than against chains() or solve_greedy.
"""

import numpy as np
import pytest

from tps5d.core.schema import Strategy, Cohort, Facility
from tps5d.allocator.dominance import hull
from tps5d.allocator.solve import solve_lp
from tps5d.generator.synth import arm_cohort

N_FX, TAU0 = 30, 34.2
# M and A: order of magnitude of the reference study's lung values. X, the scale
# of the photon adaptation benefit, is illustrative and has no source. The
# checks are closed forms in these symbols and hold for any positive values.
M, A, X = 0.069, 0.038, 0.030
DTAU_XT = 16.0

def w_of(lam_xt, x = X):
    """Photon outside-option value at the photon price.

    One adapted photon rung, so the maximum over rungs is a single term,
    floored at zero by the free non-adapted arm.
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

# T14

def _pt_na_hull_check(cohort, fac, tol_rel = 1e-6):
    """Per patient: does PT-NA sit on the augmented proton hull, and does
    that agree with the closed-form threshold at the solver's own lambda_xt?

    Single-scheme cohort required: with two schemes pooled on the proton
    axis the augmented hull answers a different question, cross-scheme
    competition, that Section 6.5 states explicitly it does not cover.

    Returns (n_checked, mismatches). A patient within relative tolerance of
    its own threshold is excluded, as in
    test_w_at_the_solver_price_reproduces_the_solver_photon_choice: the
    solver may legitimately return either rung there, so the comparison is
    not well posed at that point.
    """
    lp = solve_lp(cohort, fac)
    n_checked, mismatches = 0, []
    for pid, opts in cohort.by_patient().items():
        pt = [s for s in opts if s.modality == 'pt']
        na = next(s for s in pt if not s.adapted)
        ad = next(s for s in pt if s.adapted)
        m, a = cohort.dntcp(na), cohort.dntcp(ad) - cohort.dntcp(na)
        tau0, dtau = na.tau_pt, ad.tau_pt - na.tau_pt

        xta = [s for s in opts if s.modality == 'xt' and s.adapted]
        x = max((cohort.dntcp(s) for s in xta), default = 0.0)
        occ_xt = max((s.occ_xt for s in xta), default = 0.0)
        w = max(0.0, x - lp.lam_xt * occ_xt)

        thr = np.inf if w >= m else tau0 * a / (m - w)
        if np.isfinite(thr) and abs(dtau - thr) <= thr * tol_rel:
            continue

        on_hull = 1 in hull([(0.0, w), (na.occ_pt, m), (ad.occ_pt, m + a)])
        n_checked += 1
        if on_hull != (dtau >= thr):
            mismatches.append(pid)
    return n_checked, mismatches

# Wide, randomised sweep rather than a hand-picked borderline cohort: the
# point is that the crossing is a robust property of the formulation, not an
# artefact of a cohort built to straddle it. x_gain = 0.0 exercises the
# uncoupled case, w == 0 identically. The photon budget is swept as a
# fraction of the cohort's own photon demand, the normalised axis already
# used elsewhere (allocator design 5.2; report.sweep_budget_xt), because a
# budget sampled in raw minutes sits, for these magnitudes, close enough to
# the point where lambda_xt clears every patient's x that w collapses to 0
# almost everywhere: the coupled term of the closed form would then go
# largely unexercised despite the wide sweep in dtau.
T14_DTAU = [2.0, 8.0, 15.0, 25.0, 40.0, 60.0]
T14_XGAIN = [0.0, 0.015, 0.03]
T14_CXT_FRAC = [0.0, 0.3, 0.7, 1.0]

@pytest.mark.parametrize('cxt_frac', T14_CXT_FRAC)
@pytest.mark.parametrize('dtau', T14_DTAU)
@pytest.mark.parametrize('x_gain', T14_XGAIN)
def test_t14_hull_membership_matches_the_closed_form(x_gain, dtau, cxt_frac):
    rng = np.random.default_rng(hash((x_gain, dtau, cxt_frac)) % (2**32))
    cohort = arm_cohort(15, dtau = dtau, x_gain = x_gain, dtau_xt = 16.0,
                        seed = int(rng.integers(0, 10_000)))
    cap_pt = float(rng.uniform(150.0, 500.0))
    cap_xt = cxt_frac * cohort.demand_xt() / 12 if x_gain > 0.0 else 0.0
    fac = Facility(cap_pt, cap_xt, days = 12)

    n_checked, mismatches = _pt_na_hull_check(cohort, fac)
    assert n_checked > 0, "fixture produced nothing to check"
    assert not mismatches, f"hull membership disagreed with the closed form for {mismatches}"



# Two schedules: the closed forms of allocator 6.2 on generated cohorts (SC-07)
#
# Patient-wise, against dominance.hull on the proton chain, with each patient's
# own modality benefit m and adaptation benefit a read off the generated
# strategies. The comparison is against the hull the allocator computes.

def _proton_hull_sids(cohort, pid):
    from tps5d.allocator.dominance import hull
    chain = [s for s in cohort.by_patient()[pid] if s.tau_xt == 0.0]
    keep = hull([(s.occ_pt, cohort.dntcp(s)) for s in chain])
    return {chain[i].sid for i in keep}

def _m_and_a(cohort, pid):
    by = {s.sid: s for s in cohort.by_patient()[pid]}
    m = cohort.dntcp(by['pt'])
    return m, cohort.dntcp(by['pta']) - m

@pytest.mark.parametrize('dtau', [5.0, 30.0])
@pytest.mark.parametrize('a_mult', [1.5, 2.5])
@pytest.mark.parametrize('pen', [0.0, 0.02, 0.06])
def test_pen_star_decides_whether_the_standard_adapted_arm_is_on_the_hull(pen, a_mult, dtau):
    """Allocator 6.2: PT-A standard is on the pooled hull iff pen > pen* =
    a (a_mult - 1), patient-wise, whatever dtau."""
    from tps5d.generator.synth import two_scheme_cohort
    cohort = two_scheme_cohort(n = 12, dtau = dtau, shape = dict(pen = pen, a_mult = a_mult), seed = 4)
    checked = 0
    for pid in cohort.pids:
        _, a = _m_and_a(cohort, pid)
        star = a * (a_mult - 1.0)
        if abs(pen - star) < 1e-9:
            continue
        assert ('pta' in _proton_hull_sids(cohort, pid)) == (pen > star), (pid, pen, star)
        checked += 1
    assert checked >= 10

@pytest.mark.parametrize('a_mult', [1.5, 2.0])
@pytest.mark.parametrize('dtau', [5.0, 15.0, 60.0])
def test_hypofractionated_non_adapted_arm_obeys_the_per_schedule_threshold(dtau, a_mult):
    """Allocator 6.2: with pen = 0 and a_mult > 1 the standard adapted arm is
    below the pooled hull, so the hypofractionated chain is the frontier and
    PT-NA hyp is on the hull iff dtau >= tau0_hyp a a_mult / m, with tau0_hyp =
    tau_mult tau0 (generator defaults 1.5 and 30)."""
    from tps5d.generator.synth import two_scheme_cohort
    cohort = two_scheme_cohort(n = 12, dtau = dtau, tau0 = 30.0, tau_mult = 1.5,
                               shape = dict(pen = 0.0, a_mult = a_mult), seed = 4)
    checked = 0
    for pid in cohort.pids:
        m, a = _m_and_a(cohort, pid)
        assert 'pta' not in _proton_hull_sids(cohort, pid)
        star = 1.5 * 30.0 * a * a_mult / m
        if abs(dtau - star) < 1e-6:
            continue
        assert ('pth' in _proton_hull_sids(cohort, pid)) == (dtau > star), (pid, dtau, star)
        checked += 1
    assert checked >= 10
