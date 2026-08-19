"""Dominance removal and incremental efficiencies.

The linear relaxation of a multiple-choice knapsack is solved by upgrading
patients one rung at a time, in decreasing order of incremental efficiency. For
that ordering to be valid, each patient's option set must first be reduced to
the upper convex hull of its (cost, utility) points: an option strictly below
the hull is never selected by the LP, because a convex combination of its
neighbours beats it at the same cost.

This is the step that makes greedy allocation safe. A non-concave benefit
profile produces options below the hull, which are removed here rather than
mis-ranked later.

Under two resources the reductions are scoped **chain by chain** (allocator
design, Section 5.2): each chain lies on a single cost axis, so the hull
argument is unchanged within a chain, and no hull is taken across chains.
`chains` and `ladders` build the proton chain, on the proton cost axis, which
is what the greedy heuristics rank under the adopted convention. The photon
chain is not ranked by any heuristic; policies spend the photon budget by a
separate rule.
"""

from collections import namedtuple

# Points closer than this to the hull are treated as lying on it and removed.
# Utilities are probabilities and costs are minutes, so the natural scale of a
# cross product is small; the tolerance is deliberately tight.
TOL = 1e-12

Upgrade = namedtuple('Upgrade', 'pid rank dcost dutil eff')

def _cross(a, b, c):
    """Twice the signed area of (a, b, c). Positive if b lies below the line ac."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

def pareto(pts):
    """Indices of the non-dominated points, by increasing cost.

    Among points of equal cost only the best utility survives, and a point that
    costs more without buying more is dropped. Utility is strictly increasing
    along the result.

    This reduction is valid for both the linear and the integer problem. The
    hull reduction below is valid only for the linear one.
    """
    order = sorted(range(len(pts)), key=lambda i: (pts[i][0], -pts[i][1]))

    front, best = [], None
    for i in order:
        c, u = pts[i]
        if front and c == pts[front[-1]][0]:
            continue                      # equal cost, worse utility
        if best is not None and u <= best + TOL:
            continue                      # costs more, buys nothing
        front.append(i)
        best = u
    return front

def hull(pts):
    """Indices of the points on the upper convex hull, by increasing cost.

    pts   sequence of (cost, utility)

    The Pareto frontier is taken first, then the upper hull of that frontier.
    Collinear points are removed, so an option lying exactly on a segment
    between two others does not appear; it is an alternative optimum, not an
    additional one.

    An option below the hull is never selected by the **linear** relaxation,
    because a convex combination of its neighbours beats it at the same cost.
    It may well appear in the integer optimum, so this reduction must not be
    applied before an integer solve.
    """
    front = pareto(pts)

    keep = []
    for i in front:
        while len(keep) >= 2 and _cross(pts[keep[-2]], pts[keep[-1]], pts[i]) >= -TOL:
            keep.pop()
        keep.append(i)
    return keep

def _proton_chain(opts):
    """The options on the proton cost axis: XT-NA and the proton rungs.

    Photon-adapted options consume the other budget and are not part of this
    chain; the heuristics that rank proton upgrades never see them.
    """
    return [s for s in opts if s.tau_xt == 0.0]

def chains(cohort):
    """Per-patient Pareto-reduced proton chains, in increasing proton cost.

    Used by the integer greedy, which must not see the hull reduction.
    """
    out = {}
    for pid, opts in cohort.by_patient().items():
        chain = _proton_chain(opts)
        pts = [(s.occ_pt, cohort.dntcp(s)) for s in chain]
        out[pid] = [chain[i] for i in pareto(pts)]
    return out

def ladders(cohort):
    """Per-patient hull of the proton chain and the upgrades between rungs.

    Returns (kept, ups) where kept maps a patient to its surviving strategies in
    increasing proton cost, and ups is the flat list of upgrades across all
    patients. Within a patient the efficiencies decrease by construction of the
    hull.
    """
    kept, ups = {}, []
    for pid, opts in cohort.by_patient().items():
        chain = _proton_chain(opts)
        pts = [(s.occ_pt, cohort.dntcp(s)) for s in chain]
        idx = hull(pts)
        kept[pid] = [chain[i] for i in idx]
        for r in range(1, len(kept[pid])):
            dc = kept[pid][r].occ_pt - kept[pid][r - 1].occ_pt
            du = cohort.dntcp(kept[pid][r]) - cohort.dntcp(kept[pid][r - 1])
            ups.append(Upgrade(pid, r, dc, du, du / dc))
    return kept, ups
