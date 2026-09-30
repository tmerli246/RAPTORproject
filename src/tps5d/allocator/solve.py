"""Capacity-constrained allocation of treatment strategies.

Each patient receives exactly one strategy, subject to a proton machine
capacity constraint and a photon adaptation capacity constraint. This is a
multiple-choice knapsack problem (MCKP) with two resources.

The ILP, the LP and the greedy solvers maximise the sum of delta NTCP; the
dynamic program minimises the sum of absolute union NTCP. Since each patient
takes exactly one strategy, the baseline sum is a constant and the two are the
same problem (test T5).

No constraint of the form delta NTCP >= 0 is imposed, here or anywhere else.
Where a patient has an assignable option that is free on both budgets and has
zero utility, which is the reference arm in the normal case, that option
dominates every option of negative utility: substituting it improves the
objective and relaxes both capacity rows at once. The sign is therefore
enforced by the structure of the option set rather than by a constraint, and
adding the constraint explicitly would be redundant and would corrupt the
reading of the duals by introducing rows whose multipliers mix into them.
Where no such option exists, `Cohort.no_free_option` reports it and a negative
delta NTCP in the optimum is the correct answer, not a defect.

Solver structure:

    solve_exact      integer linear program (scipy HiGHS). The reference
                     solver: with two constraints an ILP is simpler to state
                     correctly than a 2D dynamic program
    solve_lp         the same model with integrality dropped. The duals of the
                     two capacity rows are (lambda_pt, lambda_xt) directly
    solve_dp         dynamic program, single-resource, the independent
                     cross-check at C_XT = 0 (T8)
    solve_lp_greedy  greedy relaxation on the proton chain, the independent
                     cross-check of solve_lp at C_XT = 0
    solve_greedy     the integer heuristic behind P2b: proton chain only,
                     under the adopted ranking convention
"""

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog, milp, LinearConstraint, Bounds

from tps5d.core.schema import Allocation, LPSolution
from tps5d.allocator.dominance import ladders, chains

# Machine time is discretised before the dynamic program. The resolution is not
# innocuous: at 1 min, an occupancy of 36.9 min rounds to 37 and 13 patients no
# longer fit in 480 min, which changes the answer. 0.1 min is fine for realistic
# session lengths and keeps the state space small.
RES = 0.1

# Weights within this distance of 0 or 1 are read as integral in LP solutions.
W_TOL = 1e-7

# Relative optimality gap of the integer solver. HiGHS defaults to 1e-4, which
# on non-concave cohorts left a shortfall on the cohort sum of up to 3e-4 at
# P = 200 and 3e-3 at P = 1000 in the cases tested. 1e-6 matched the zero-gap
# objective at P = 200. Run time grows with P and depends on the instance: at
# P = 1000 one generated cohort solved in 3 s and another did not finish in
# 150 s, where 1e-4 took 0.6 s. Pass a looser `mip_rel_gap` at that size.
MIP_REL_GAP = 1e-6

def _units(minutes, res = RES):
    """Machine time in integer units of `res` minutes, rounded up for costs."""
    return int(np.ceil(minutes / res - 1e-9))

def _columns(cohort):
    """Flat (pid, strategy) columns and the index range of each patient."""
    opts, cols = cohort.by_patient(), []
    for pid in cohort.pids:
        if not opts[pid]:
            raise ValueError(f"{pid}: empty option set, every strategy failed "
                             f"the admissibility screens")
        cols += [(pid, s) for s in opts[pid]]
    return cols

def _model(cohort, facility):
    """Shared LP/ILP model: minimise -utility under the two capacity rows and
    one assignment row per patient."""
    cols = _columns(cohort)
    c = np.array([-cohort.dntcp(s) for _, s in cols])

    a_ub = np.array([[s.occ_pt for _, s in cols],
                     [s.occ_xt for _, s in cols]])
    b_ub = np.array([facility.budget_pt, facility.budget_xt])

    # One assignment row per patient, sparse: P x (sum of option counts).
    pids = cohort.pids
    row = {pid: i for i, pid in enumerate(pids)}
    r = np.array([row[pid] for pid, _ in cols])
    a_eq = sp.csr_array((np.ones(len(cols)), (r, np.arange(len(cols)))),
                        shape = (len(pids), len(cols)))
    b_eq = np.ones(len(pids))
    return cols, c, a_ub, b_ub, a_eq, b_eq

def _wrap_choice(cohort, choice, gap = None):
    used_pt = sum(s.occ_pt for s in choice.values())
    used_xt = sum(s.occ_xt for s in choice.values())
    mean = np.mean([cohort.dntcp(s) for s in choice.values()])
    return Allocation(choice = choice, used_pt = used_pt, used_xt = used_xt,
                      mean_dntcp = mean, gap = gap)

def solve_exact(cohort, facility, mip_rel_gap = MIP_REL_GAP):
    """Two-resource MCKP optimum, by integer linear programming, to a relative
    gap of `mip_rel_gap` (default 1e-6; 0 is exact and can be slow beyond a few
    hundred patients).

    Returns an Allocation whose `gap` is the relative gap the solver reports at
    termination. Feasibility is guaranteed whenever every patient
    has an assignable option that is free on both budgets, since the model can
    then always fall back to it. That holds in the normal case, where the
    reference arm is assignable. It does not hold once the coverage screen has
    removed a patient's reference arm, so infeasibility is reported with the
    patients responsible rather than as a bare solver message.
    """
    cols, c, a_ub, b_ub, a_eq, b_eq = _model(cohort, facility)

    res = milp(c,
               constraints = [LinearConstraint(a_ub, ub = b_ub),
                              LinearConstraint(a_eq, lb = b_eq, ub = b_eq)],
               integrality = np.ones(len(cols)),
               bounds = Bounds(0, 1),
               options = {'mip_rel_gap': mip_rel_gap})
    if not res.success:
        raise RuntimeError(f"milp failed: {res.message}. "
                           f"Patients without a free assignable option: "
                           f"{cohort.no_free_option()}")

    choice = {}
    for (pid, s), x in zip(cols, res.x):
        if x > 0.5:
            if pid in choice:
                raise RuntimeError(f"{pid}: two options selected")
            choice[pid] = s
    if len(choice) != len(cohort.pids):
        missing = [pid for pid in cohort.pids if pid not in choice]
        raise RuntimeError(f"solve_exact: no option selected for {missing}")
    gap = getattr(res, 'mip_gap', None)
    return _wrap_choice(cohort, choice, None if gap is None else float(gap))

def solve_lp(cohort, facility):
    """Linear relaxation of the same model, with the shadow prices read from
    the HiGHS duals of the two capacity rows.

    linprog minimises, so the marginal of a binding <= row is non-positive and
    the shadow price of the maximisation problem is its negation. At most one
    fractional class per binding constraint appears generically, so `frac`
    holds at most two entries.
    """
    cols, c, a_ub, b_ub, a_eq, b_eq = _model(cohort, facility)

    res = linprog(c, A_ub = a_ub, b_ub = b_ub, A_eq = a_eq, b_eq = b_eq,
                  bounds = (0, 1), method = 'highs')
    if not res.success:
        raise RuntimeError(f"linprog failed: {res.message}")

    lam_pt = max(0.0, -res.ineqlin.marginals[0])
    lam_xt = max(0.0, -res.ineqlin.marginals[1])

    # Integral part: the largest-weight option per patient. Fractional entries
    # are reported separately.
    weight, choice, frac = {}, {}, []
    for (pid, s), x in zip(cols, res.x):
        if x > weight.get(pid, -1.0):
            weight[pid], choice[pid] = x, s
        if W_TOL < x < 1.0 - W_TOL:
            frac.append((pid, s.sid, float(x)))

    used = a_ub @ res.x
    return LPSolution(value = -res.fun, lam_pt = lam_pt, lam_xt = lam_xt,
                      used_pt = float(used[0]), used_xt = float(used[1]),
                      choice = choice, frac = frac)

def solve_dp(cohort, facility, res = RES):
    """Exact solver: dynamic programming over discretised proton minutes.
    Single-resource by construction, the independent cross-check of the ILP at
    C_XT = 0 (test T8).

    Raises if any option consumes the photon adaptation budget; restrict the
    cohort to tau_xt == 0 first, which is exactly the C_XT = 0 problem.
    """
    opts = cohort.by_patient()
    for pid, o in opts.items():
        if not o:
            raise ValueError(f"{pid}: empty option set, every strategy failed "
                             f"the admissibility screens")
        if any(s.tau_xt > 0.0 for s in o):
            raise ValueError("solve_dp is single-resource; restrict to "
                             "tau_xt == 0 or use solve_exact")

    cap = int(np.floor(facility.budget_pt / res + 1e-9))
    pids = cohort.pids

    # dp[c] is the best objective over the patients processed so far, using at
    # most c units of capacity. Objective is -sum(ntcp_tot), maximised.
    dp = np.zeros(cap + 1)
    back = np.full((len(pids), cap + 1), -1, dtype = np.int16)

    for i, pid in enumerate(pids):
        new = np.full(cap + 1, -np.inf)
        for j, s in enumerate(opts[pid]):
            cost = _units(s.occ_pt, res)
            if cost > cap:
                continue
            cand = dp[:cap + 1 - cost] - s.ntcp_tot
            take = cand > new[cost:]
            new[cost:][take] = cand[take]
            back[i, cost:][take] = j
        if not np.isfinite(new[cap]):
            raise ValueError(f"{pid}: no strategy fits the remaining capacity")
        dp = new

    # Walk the decisions back from the full capacity.
    choice = {}
    c = cap
    for i in reversed(range(len(pids))):
        pid = pids[i]
        j = back[i, c]
        if j < 0:
            raise RuntimeError(f"{pid}: backtracking entered an unreachable state")
        s = opts[pid][j]
        choice[pid] = s
        c -= _units(s.occ_pt, res)

    return _wrap_choice(cohort, choice)

def solve_lp_greedy(cohort, facility):
    """Linear relaxation: greedy upgrading on the proton chain after dominance
    removal. The independent cross-check of solve_lp at C_XT = 0; with
    photon-adapted options present it solves that limit, since the proton chain
    excludes them.

    Every patient starts on its cheapest surviving option, which is normally
    the reference arm at zero proton cost. Capacity is then spent on the
    pooled upgrades in decreasing order of incremental efficiency. At most one
    upgrade is taken fractionally, and its efficiency is the shadow price.

    The starting value is the sum of the utilities of those cheapest options,
    which is zero in the normal case and can be negative where a reference arm
    is inadmissible. The upgrades themselves are unaffected, since they are
    differences.
    """
    kept, ups = ladders(cohort)

    choice = {pid: chain[0] for pid, chain in kept.items()}
    used = sum(s.occ_pt for s in choice.values())
    if used > facility.budget_pt + 1e-9:
        raise ValueError("cheapest options already exceed capacity")

    value = sum(cohort.dntcp(s) for s in choice.values())
    left = facility.budget_pt - used
    frac, lam = [], 0.0

    # Within a patient the hull makes efficiencies decrease with rank, so a
    # global scan in decreasing efficiency reaches a patient's upgrades in
    # order. No predecessor check is needed here, unlike in the integer greedy.
    for up in sorted(ups, key = lambda u: -u.eff):
        if up.dcost <= left + 1e-9:
            choice[up.pid] = kept[up.pid][up.rank]
            value += up.dutil
            left -= up.dcost
        else:
            w = left / up.dcost
            value += w * up.dutil
            frac = [(up.pid, kept[up.pid][up.rank].sid, w)]
            lam = up.eff
            left = 0.0
            break

    return LPSolution(value = value, lam_pt = lam, lam_xt = 0.0,
                      used_pt = facility.budget_pt - left, used_xt = 0.0,
                      choice = choice, frac = frac,
                      kept = {p: [s.sid for s in c] for p, c in kept.items()})

def solve_greedy(cohort, facility):
    """Integer allocation by best available upgrade on the proton chain.

    Every patient starts on its cheapest option. At each step the upgrade with
    the highest ratio of utility gained to minutes spent is taken, over all
    patients and over every option above the one they currently hold. The
    procedure stops when no upgrade fits.

    Under the adopted ranking convention the heuristic ranks proton upgrades
    only; the photon budget is spent by the separate rule in policies.py.

    Two differences from the linear relaxation matter.

    The hull reduction is **not** applied. An option below the hull is never
    bought by the LP, which can split its budget between the neighbours, but the
    integer problem cannot split and may well want it.

    Upgrades are not restricted to the next option up. On a non-concave chain
    the best available upgrade can skip several rungs, and a rank-by-rank scan
    in decreasing efficiency would never reach it.

    The sign guard below is on the incremental utility, not on the level. An
    upgrade must improve on what the patient currently holds; it need not
    improve on the reference arm, which may itself be unavailable.
    """
    chain = chains(cohort)

    choice = {pid: c[0] for pid, c in chain.items()}
    rank = {pid: 0 for pid in chain}
    left = facility.budget_pt - sum(s.occ_pt for s in choice.values())
    if left < -1e-9:
        raise ValueError("cheapest options already exceed capacity")

    while True:
        best = None
        for pid, c in chain.items():
            here = c[rank[pid]]
            for j in range(rank[pid] + 1, len(c)):
                dc = c[j].occ_pt - here.occ_pt
                if dc > left + 1e-9:
                    break                       # chain is sorted by cost
                du = cohort.dntcp(c[j]) - cohort.dntcp(here)
                if best is None or du / dc > best[0]:
                    best = (du / dc, pid, j, dc)
        if best is None:
            break
        _, pid, j, dc = best
        choice[pid] = chain[pid][j]
        rank[pid] = j
        left -= dc

    return _wrap_choice(cohort, choice)
