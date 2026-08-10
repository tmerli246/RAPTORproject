"""Reporting layer for the allocator.

Turns allocations into the quantities the paper reports. Nothing here computes
an allocation; it summarises one. Kept separate from solve.py so that the
solvers stay free of presentation concerns and so that a change to what is
reported never risks changing what is solved.

The reported quantities, and where each is committed to:

    cohort mean delta NTCP per policy      
    shadow price lambda                    
    Pareto and LP dominance counts         
    cohort composition by arm              
    per-endpoint delta NTCP                
"""

import csv

import numpy as np

from tps5d.allocator.solve import solve_lp
from tps5d.allocator.dominance import pareto, hull

def arm_label(s):
    """Short label for the arm a strategy belongs to."""
    if s.modality == 'xt':
        return 'photons'
    return f"PT, {s.n_adapt} adapt" if s.n_adapt else "PT, no adapt"

def summarise(cohort, alloc, facility = None):
    """Scalars describing one allocation.

    Returns a flat dict, so that a sweep is a list of dicts and writes to CSV
    without further shaping.
    """
    chosen = list(alloc.choice.values())
    rec = {
        'mean_dntcp': alloc.mean_dntcp,
        'n_patients': len(chosen),
        'n_pt': sum(1 for s in chosen if s.modality == 'pt'),
        'n_adapt_total': sum(s.n_adapt for s in chosen),
        'used_min': alloc.used,
    }
    if facility is not None:
        rec['budget_min'] = facility.budget
        rec['utilisation'] = alloc.used / facility.budget if facility.budget else 0.0

    # Per-endpoint mean delta NTCP, for the reporting table. Selection uses the
    # union scalar; these are reported alongside it, never selected on.
    keys = sorted({k for s in chosen for k in s.ntcp})
    base = cohort.baseline()
    for k in keys:
        rec[f'dntcp_{k}'] = float(np.mean(
            [base[s.pid].ntcp[k] - s.ntcp[k] for s in chosen]))

    for lab in sorted({arm_label(s) for s in chosen}):
        rec[f'n_{lab}'] = sum(1 for s in chosen if arm_label(s) == lab)
    return rec

def dominance_counts(cohort):
    """Options removed by each reduction, per patient and in total.

    The two are reported separately because they mean different things. Pareto
    dominance says two arms are not in genuine competition, which is structural
    and largely uninformative. LP dominance says an adaptation count is one the
    relaxation would never buy at any capacity, which is the clinically
    informative statement. One combined count would let the first swamp the
    second.
    """
    per_patient, tot = {}, {'n_options': 0, 'n_pareto': 0, 'n_lp': 0}
    for pid, opts in cohort.by_patient().items():
        pts = [(s.occupancy, cohort.dntcp(s)) for s in opts]
        n_par, n_hull = len(pareto(pts)), len(hull(pts))
        per_patient[pid] = {'n_options': len(opts),
                            'n_pareto_dominated': len(opts) - n_par,
                            'n_lp_dominated': n_par - n_hull}
        tot['n_options'] += len(opts)
        tot['n_pareto'] += len(opts) - n_par
        tot['n_lp'] += n_par - n_hull
    return per_patient, tot

def sweep(make_cohort, facility, dtaus, policies):
    """Run every policy across a range of adaptation times.

    make_cohort : callable dtau -> Cohort. Adaptation time changes occupancy,
                  so the cohort is rebuilt at each point rather than reweighted
    policies    : dict of name -> callable (cohort, facility) -> Allocation

    Returns a list of dicts, one per (dtau, policy).
    """
    out = []
    for dt in dtaus:
        cohort = make_cohort(dt)
        lam = solve_lp(cohort, facility).lam
        _, dom = dominance_counts(cohort)
        for name, fn in policies.items():
            rec = {'dtau': dt, 'policy': name, 'lambda': lam}
            rec.update(summarise(cohort, fn(cohort, facility), facility))
            rec.update({'n_lp_dominated': dom['n_lp'],
                        'n_pareto_dominated': dom['n_pareto']})
            out.append(rec)
    return out

def to_csv(records, path):
    """Write sweep records to CSV, union of keys as the header."""
    keys = []
    for r in records:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, 'w', newline = '') as f:
        w = csv.DictWriter(f, fieldnames = keys)
        w.writeheader()
        w.writerows(records)
    return path