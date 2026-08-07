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

def chains(cohort):
    """Per-patient Pareto-reduced option chains, in increasing cost.

    Used by the integer greedy, which must not see the hull reduction.
    """
    out = {}
    for pid, opts in cohort.by_patient().items():
        pts = [(s.occupancy, cohort.dntcp(s)) for s in opts]
        out[pid] = [opts[i] for i in pareto(pts)]
    return out

def ladders(cohort):
    """Per-patient hull options and the upgrades between them.

    Returns (kept, ups) where kept maps a patient to its surviving strategies in
    increasing cost, and ups is the flat list of upgrades across all patients.
    Within a patient the efficiencies decrease by construction of the hull.
    """
    kept, ups = {}, []
    for pid, opts in cohort.by_patient().items():
        pts = [(s.occupancy, cohort.dntcp(s)) for s in opts]
        idx = hull(pts)
        chain = [opts[i] for i in idx]
        kept[pid] = chain
        for r in range(1, len(chain)):
            dc = chain[r].occupancy - chain[r - 1].occupancy
            du = cohort.dntcp(chain[r]) - cohort.dntcp(chain[r - 1])
            ups.append(Upgrade(pid, r, dc, du, du / dc))
    return kept, ups