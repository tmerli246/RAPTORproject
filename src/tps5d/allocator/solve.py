"""Capacity-constrained allocation of treatment strategies.

Each patient receives exactly one strategy, subject to a proton machine
capacity constraint. This is a multiple-choice knapsack problem (MCKP), solved
exactly by dynamic programming over discretised machine time.

The objective is the sum of absolute union NTCP, minimised. Since each patient
takes exactly one strategy, the baseline sum is a constant, so this is the same
problem as maximising the sum of delta NTCP (test T5). Solving on absolute NTCP
keeps the baseline out of the optimisation.
"""

import numpy as np

from tps5d.core.schema import Allocation, LPSolution
from tps5d.allocator.dominance import ladders, chains

# Machine time is discretised before the dynamic program. The resolution is not
# innocuous: at 1 min, an occupancy of 36.9 min rounds to 37 and 13 patients no
# longer fit in 480 min, which changes the answer. 0.1 min is fine for realistic
# session lengths and keeps the state space small.
RES = 0.1


def _units(minutes, res=RES):
    """Machine time in integer units of `res` minutes, rounded up for costs."""
    return int(np.ceil(minutes / res - 1e-9))


def solve_exact(cohort, facility, res=RES):
    """Exact MCKP solution.

    Returns an Allocation. Raises if any patient has an empty option set.
    """
    opts = cohort.by_patient()
    for pid, o in opts.items():
        if not o:
            raise ValueError(f"{pid}: empty option set, no admissible strategy")

    cap = int(np.floor(facility.budget / res + 1e-9))
    pids = cohort.pids

    # dp[c] is the best objective over the patients processed so far, using at
    # most c units of capacity. Objective is -sum(ntcp_tot), maximised.
    dp = np.zeros(cap + 1)
    back = np.zeros((len(pids), cap + 1), dtype=np.int16)

    for i, pid in enumerate(pids):
        new = np.full(cap + 1, -np.inf)
        for j, s in enumerate(opts[pid]):
            cost = _units(s.occupancy, res)
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
        s = opts[pid][back[i, c]]
        choice[pid] = s
        c -= _units(s.occupancy, res)

    used = sum(s.occupancy for s in choice.values())
    mean = np.mean([cohort.dntcp(s) for s in choice.values()])
    return Allocation(choice=choice, used=used, mean_dntcp=mean)


def solve_lp(cohort, facility):
    """Linear relaxation, solved by greedy upgrading after dominance removal.

    Every patient starts on its cheapest surviving option, which is normally the
    photon strategy at zero proton cost. Capacity is then spent on the pooled
    upgrades in decreasing order of incremental efficiency. At most one upgrade
    is taken fractionally, and its efficiency is the shadow price.
    """
    kept, ups = ladders(cohort)

    choice = {pid: chain[0] for pid, chain in kept.items()}
    used = sum(s.occupancy for s in choice.values())
    if used > facility.budget + 1e-9:
        raise ValueError("cheapest options already exceed capacity")

    value = sum(cohort.dntcp(s) for s in choice.values())
    left = facility.budget - used
    frac, lam = None, 0.0

    # Within a patient the hull makes efficiencies decrease with rank, so a
    # global scan in decreasing efficiency reaches a patient's upgrades in
    # order. No predecessor check is needed here, unlike in the integer greedy.
    for up in sorted(ups, key=lambda u: -u.eff):
        if up.dcost <= left + 1e-9:
            choice[up.pid] = kept[up.pid][up.rank]
            value += up.dutil
            left -= up.dcost
        else:
            w = left / up.dcost
            value += w * up.dutil
            frac = (up.pid, kept[up.pid][up.rank].sid, w)
            lam = up.eff
            left = 0.0
            break

    return LPSolution(value=value, lam=lam, used=facility.budget - left,
                      choice=choice, frac=frac, kept={p: [s.sid for s in c]
                                                      for p, c in kept.items()})


def solve_greedy(cohort, facility):
    """Integer allocation by best available upgrade.

    Every patient starts on its cheapest option. At each step the upgrade with
    the highest ratio of utility gained to minutes spent is taken, over all
    patients and over every option above the one they currently hold. The
    procedure stops when no upgrade fits.

    Two differences from the linear relaxation matter, and version 1 of this
    function got both wrong by reusing the LP machinery.

    The hull reduction is **not** applied. An option below the hull is never
    bought by the LP, which can split its budget between the neighbours, but the
    integer problem cannot split and may well want it.

    Upgrades are not restricted to the next option up. On a non-concave chain
    the best available upgrade can skip several rungs, and a rank-by-rank scan
    in decreasing efficiency would never reach it.
    """
    chain = chains(cohort)

    choice = {pid: c[0] for pid, c in chain.items()}
    rank = {pid: 0 for pid in chain}
    left = facility.budget - sum(s.occupancy for s in choice.values())
    if left < -1e-9:
        raise ValueError("cheapest options already exceed capacity")

    while True:
        best = None
        for pid, c in chain.items():
            here = c[rank[pid]]
            for j in range(rank[pid] + 1, len(c)):
                dc = c[j].occupancy - here.occupancy
                if dc > left + 1e-9:
                    break                       # chain is sorted by cost
                du = cohort.dntcp(c[j]) - cohort.dntcp(here)
                if du <= 0:
                    continue
                if best is None or du / dc > best[0]:
                    best = (du / dc, pid, j, dc)
        if best is None:
            break
        _, pid, j, dc = best
        choice[pid] = chain[pid][j]
        rank[pid] = j
        left -= dc

    used = sum(s.occupancy for s in choice.values())
    mean = np.mean([cohort.dntcp(s) for s in choice.values()])
    return Allocation(choice=choice, used=used, mean_dntcp=mean)

