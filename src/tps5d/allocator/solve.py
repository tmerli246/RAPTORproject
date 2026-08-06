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

from tps5d.core.schema import Allocation

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
