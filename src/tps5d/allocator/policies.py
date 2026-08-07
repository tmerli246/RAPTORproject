"""Allocation policies, from current practice to the exact optimum.

An optimum alone is not a clinically useful output, because no clinic implements
an integer program. The informative output is the gap between what simple rules
achieve and what is achievable at all:

    P3 - P0    total headroom
    P2b - P0   what a correct implementable rule captures
    P3 - P2b   whether exact optimisation is worth anything
    P2b - P2a  the cost of ranking on the wrong statistic

All policies share the signature (cohort, facility) -> Allocation, so they can
be run on identical inputs and differenced directly.
"""

import numpy as np

from tps5d.core.schema import Allocation
from tps5d.allocator.solve import solve_exact, solve_greedy

# Referral threshold on union delta NTCP, used by the threshold-based policies.
# The Dutch protocols set per-endpoint thresholds by national policy. Zero means
# refer any patient who benefits at all, so that the capacity constraint rather
# than the threshold is what binds. It is a parameter, not a finding.
THRESHOLD = 0.0

def _wrap(cohort, choice):
    """Package a per-patient choice as an Allocation."""
    used = sum(s.occupancy for s in choice.values())
    mean = np.mean([cohort.dntcp(s) for s in choice.values()])
    return Allocation(choice = choice, used = used, mean_dntcp = mean)

def _refer(cohort, facility, pick, threshold = THRESHOLD):
    """Model-based selection: rank patients by benefit, refer until full.

    `pick` selects the proton strategy a referred patient would receive. This is
    the structure of both current practice and the reference study; they differ
    only in which strategy that is.
    """
    choice = dict(cohort.baseline())
    cand = []
    for pid, opts in cohort.by_patient().items():
        pt = [s for s in opts if s.modality == 'pt']
        if pt:
            cand.append((pid, pick(pt)))

    cand.sort(key = lambda c: cohort.dntcp(c[1]), reverse = True)

    left = facility.budget
    for pid, s in cand:
        if cohort.dntcp(s) < threshold:
            break
        if s.occupancy <= left + 1e-9:
            choice[pid] = s
            left -= s.occupancy
    return _wrap(cohort, choice)

def p0(cohort, facility, threshold = THRESHOLD):
    """Current practice: referral on delta NTCP, standard schedule, no adaptation."""
    sub = cohort.restrict(lambda s: s.n_adapt == 0 and s.scheme == 'std')
    return _refer(sub, facility, lambda pt: max(pt, key=sub.dntcp), threshold)

def p1(cohort, facility, threshold = THRESHOLD):
    """The reference study: referral, then adaptation for every proton patient."""
    sub = cohort.restrict(lambda s: s.scheme == 'std')
    return _refer(sub, facility,
                  lambda pt: max(pt, key=lambda s: (s.n_adapt, sub.dntcp(s))),
                  threshold)

def p2a(cohort, facility):
    """Greedy by benefit density over patients.

    The natural capacity-aware correction, implementable by hand: rank every
    candidate strategy by delta NTCP per machine-minute and assign it if the
    patient is still unassigned and it fits. It is not optimal, because it ranks
    whole strategies rather than the upgrades between them, and every patient
    already holds a photon option at zero cost.
    """
    choice = dict(cohort.baseline())
    cand = [s for s in cohort.strategies if s.modality == 'pt' and s.occupancy > 0]
    cand.sort(key = lambda s: cohort.dntcp(s) / s.occupancy, reverse = True)

    left, taken = facility.budget, set()
    for s in cand:
        if s.pid in taken or cohort.dntcp(s) <= 0:
            continue
        if s.occupancy <= left + 1e-9:
            choice[s.pid] = s
            taken.add(s.pid)
            left -= s.occupancy
    return _wrap(cohort, choice)

def p2b(cohort, facility):
    """Greedy by incremental efficiency after dominance removal."""
    return solve_greedy(cohort, facility)

def p3(cohort, facility):
    """Exact multiple-choice knapsack optimum."""
    return solve_exact(cohort, facility)

POLICIES = {'P0': p0, 'P1': p1, 'P2a': p2a, 'P2b': p2b, 'P3': p3}

def compare(cohort, facility):
    """Run every policy on the same cohort and capacity."""
    return {name: fn(cohort, facility) for name, fn in POLICIES.items()}