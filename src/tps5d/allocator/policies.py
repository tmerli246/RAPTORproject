"""Allocation policies, from current practice to the exact optimum.

An optimum alone is not a clinically useful output, because no clinic implements
an integer program. The informative output is the gap between what simple rules
achieve and what is achievable at all:

    P3 - P0    total headroom
    P2b - P0   what a correct implementable rule captures
    P3 - P2b   whether exact optimisation is worth anything
    P2b - P2a  the cost of ranking on the wrong statistic
    P3 - P1x   the value of optimising, separated from the value of the
               adapted photon arm merely existing, which P3 - P1 confounds

All policies share the signature (cohort, facility) -> Allocation, so they can
be run on identical inputs and differenced directly.

Ranking convention under two resources (allocator design, Section 5.3): the
heuristics rank proton upgrades only, and the photon budget is spent by a
separate rule, adapting photon patients in decreasing delta NTCP until it is
exhausted. All conventions coincide at C_XT = 0, so the version 4 behaviour is
recovered by construction. P0 and P1 spend no photon budget: they are the
reference-study world, in which the adapted photon arm does not exist.
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
    used_pt = sum(s.occ_pt for s in choice.values())
    used_xt = sum(s.occ_xt for s in choice.values())
    mean = np.mean([cohort.dntcp(s) for s in choice.values()])
    return Allocation(choice = choice, used_pt = used_pt, used_xt = used_xt,
                      mean_dntcp = mean)

def spend_photon_budget(cohort, choice, budget_xt):
    """Spend the photon adaptation budget on the patients not receiving protons.

    The rule of Section 5.3: candidates are ranked by the delta NTCP of their
    best photon-adapted option, and each is upgraded to the best such option
    that fits, in decreasing order, until the budget is exhausted. Patients
    already on protons are untouched. Returns the updated choice.
    """
    cand = []
    for pid, opts in cohort.by_patient().items():
        if choice[pid].modality == 'pt':
            continue
        xta = sorted((s for s in opts if s.occ_xt > 0 and cohort.dntcp(s) > 0),
                     key = cohort.dntcp, reverse = True)
        if xta:
            cand.append((pid, xta))

    cand.sort(key = lambda c: cohort.dntcp(c[1][0]), reverse = True)

    left = budget_xt
    for pid, xta in cand:
        for s in xta:
            if s.occ_xt <= left + 1e-9:
                choice[pid] = s
                left -= s.occ_xt
                break
    return choice

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

    left = facility.budget_pt
    for pid, s in cand:
        if cohort.dntcp(s) < threshold:
            break
        if s.occ_pt <= left + 1e-9:
            choice[pid] = s
            left -= s.occ_pt
    return _wrap(cohort, choice)

def p0(cohort, facility, threshold = THRESHOLD):
    """Current practice: referral on delta NTCP, standard schedule, no adaptation."""
    sub = cohort.restrict(lambda s: s.n_adapt == 0 and s.scheme == 'std')
    return _refer(sub, facility, lambda pt: max(pt, key = sub.dntcp), threshold)

def p1(cohort, facility, threshold = THRESHOLD):
    """The reference study: referral, then adaptation for every proton patient."""
    sub = cohort.restrict(lambda s: s.scheme == 'std' and s.tau_xt == 0.0)
    return _refer(sub, facility,
                  lambda pt: max(pt, key = lambda s: (s.n_adapt, sub.dntcp(s))),
                  threshold)

def p1x(cohort, facility, threshold = THRESHOLD):
    """As P1, then photon adaptation in decreasing delta NTCP until the photon
    budget is exhausted. Isolates the value of the adapted photon arm's
    existence from the value of optimising over it."""
    alloc = p1(cohort, facility, threshold)
    choice = spend_photon_budget(cohort, dict(alloc.choice), facility.budget_xt)
    return _wrap(cohort, choice)

def p2a(cohort, facility):
    """Greedy by benefit density over patients, then the photon rule.

    The natural capacity-aware correction, implementable by hand: rank every
    candidate proton strategy by delta NTCP per machine-minute and assign it if
    the patient is still unassigned and it fits. It is not optimal, because it
    ranks whole strategies rather than the upgrades between them, and every
    patient already holds a photon option at zero cost.
    """
    choice = dict(cohort.baseline())
    cand = [s for s in cohort.strategies if s.modality == 'pt' and s.occ_pt > 0]
    cand.sort(key = lambda s: cohort.dntcp(s) / s.occ_pt, reverse = True)

    left, taken = facility.budget_pt, set()
    for s in cand:
        if s.pid in taken or cohort.dntcp(s) <= 0:
            continue
        if s.occ_pt <= left + 1e-9:
            choice[s.pid] = s
            taken.add(s.pid)
            left -= s.occ_pt
    choice = spend_photon_budget(cohort, choice, facility.budget_xt)
    return _wrap(cohort, choice)

def p2b(cohort, facility):
    """Greedy by incremental efficiency after dominance removal, on the proton
    chain, then the photon rule."""
    alloc = solve_greedy(cohort, facility)
    choice = spend_photon_budget(cohort, dict(alloc.choice), facility.budget_xt)
    return _wrap(cohort, choice)

def p3(cohort, facility):
    """Exact two-resource multiple-choice knapsack optimum."""
    return solve_exact(cohort, facility)

POLICIES = {'P0': p0, 'P1': p1, 'P1x': p1x, 'P2a': p2a, 'P2b': p2b, 'P3': p3}

def compare(cohort, facility):
    """Run every policy on the same cohort and capacity."""
    return {name: fn(cohort, facility) for name, fn in POLICIES.items()}
