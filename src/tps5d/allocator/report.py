"""Reporting layer for the allocator.

Turns allocations into the quantities the paper reports. Nothing here computes
an allocation; it summarises one. Kept separate from solve.py so that the
solvers stay free of presentation concerns and so that a change to what is
reported never risks changing what is solved.

The reported quantities, and where each is committed to:

    cohort mean delta NTCP per policy
    shadow prices lambda_pt and lambda_xt, the latter as a curve over the
    normalised photon budget
    Pareto and LP dominance counts
    cohort composition by arm
    per-endpoint delta NTCP

The sweep functions produce every candidate output of road Section 5.12
without deciding internally which one is the result: the hierarchy is a
property of the manuscript, not of the code.
"""

import csv

import numpy as np

from tps5d.core.schema import Facility
from tps5d.allocator.solve import solve_lp
from tps5d.allocator.dominance import pareto, hull

def arm_label(s):
    """Short label for the arm a strategy belongs to."""
    if s.modality == 'xt':
        return f"XT, {s.n_adapt} adapt" if s.n_adapt else "photons"
    return f"PT, {s.n_adapt} adapt" if s.n_adapt else "PT, no adapt"

def summarise(cohort, alloc, facility = None):
    """Scalars describing one allocation.

    Returns a flat dict, so that a sweep is a list of dicts and writes to CSV
    without further shaping.
    """
    chosen = list(alloc.choice.values())
    d = [cohort.dntcp(s) for s in chosen]
    rec = {
        'mean_dntcp': alloc.mean_dntcp,
        'min_dntcp': min(d),
        'n_dntcp_neg': sum(1 for v in d if v < 0.0),
        'n_patients': len(chosen),
        'n_pt': sum(1 for s in chosen if s.modality == 'pt'),
        'n_xt_adapted': sum(1 for s in chosen
                            if s.modality == 'xt' and s.n_adapt > 0),
        'n_adapt_total': sum(s.n_adapt for s in chosen),
        'used_pt_min': alloc.used_pt,
        'used_xt_min': alloc.used_xt,
    }
    if facility is not None:
        rec['budget_pt_min'] = facility.budget_pt
        rec['budget_xt_min'] = facility.budget_xt
        rec['utilisation'] = alloc.used_pt / facility.budget_pt if facility.budget_pt else 0.0
        rec['utilisation_xt'] = alloc.used_xt / facility.budget_xt if facility.budget_xt else 0.0

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

def admissibility_counts(cohort):
    """What the coverage screen removed, and whether a free fallback survived.

    Reported so that the option sets the allocator worked on are visible to a
    reader who cannot inspect them. Three quantities are separated:

        screened out          strategies the evaluator marked inadmissible.
                              Coverage is the only screen that removes
                              anything: no harm is a reported diagnostic and
                              never touches the flag (allocator design,
                              Section 8.3)
        assignable and worse  assignable strategies whose delta NTCP is not
                              positive. These are never selected while a free
                              reference arm exists, so the count measures how
                              often adaptation or a changed schedule fails to
                              help, not how often it is chosen. This is the
                              no-harm diagnostic. The reference arm itself is
                              excluded, its zero being definitional rather
                              than informative
        no free option        patients whose reference arm is not assignable.
                              Only these can be allocated a strategy worse
                              than the reference

    A cohort with no free-option violations makes the statement that no
    patient is worse off than the reference true by construction. It is then
    a property of the formulation and must be reported as such, not as a
    finding.
    """
    out = {'n_patients': len(cohort.pids), 'n_options': 0,
           'n_inadmissible': 0, 'n_dntcp_le0': 0}
    for opts in cohort.all_by_patient().values():
        out['n_options'] += len(opts)
        out['n_inadmissible'] += sum(1 for s in opts if not s.admissible)
        out['n_dntcp_le0'] += sum(1 for s in opts
                                  if s.admissible and not s.baseline
                                  and cohort.dntcp(s) <= 0.0)
    out['n_no_free_option'] = len(cohort.no_free_option())
    out['n_no_option'] = len(cohort.no_option())
    return out

def dominance_counts(cohort):
    """Options removed by each reduction, per patient and in total.

    The two are reported separately because they mean different things. Pareto
    dominance says two arms are not in genuine competition, which is structural
    and largely uninformative. LP dominance says an adaptation count is one the
    relaxation would never buy at any capacity, which is the clinically
    informative statement. One combined count would let the first swamp the
    second.

    The reductions are chain-scoped: each chain lies on one cost axis, so the
    counts are computed per chain and summed. No reduction is taken across
    chains.
    """
    per_patient, tot = {}, {'n_options': 0, 'n_pareto': 0, 'n_lp': 0}
    for pid, opts in cohort.by_patient().items():
        n_par, n_hull, n_opts = 0, 0, 0
        for cost in ('occ_pt', 'occ_xt'):
            chain = [s for s in opts
                     if (s.tau_xt == 0.0) == (cost == 'occ_pt')]
            if not chain:
                continue
            pts = [(getattr(s, cost), cohort.dntcp(s)) for s in chain]
            n_opts += len(chain)
            n_par += len(pareto(pts))
            n_hull += len(hull(pts))
        per_patient[pid] = {'n_options': n_opts,
                            'n_pareto_dominated': n_opts - n_par,
                            'n_lp_dominated': n_par - n_hull}
        tot['n_options'] += n_opts
        tot['n_pareto'] += n_opts - n_par
        tot['n_lp'] += n_par - n_hull
    return per_patient, tot

def sweep(make_cohort, facility, dtaus, policies):
    """Run every policy across a range of proton adaptation times.

    make_cohort : callable dtau -> Cohort. Adaptation time changes occupancy,
                  so the cohort is rebuilt at each point rather than reweighted
    policies    : dict of name -> callable (cohort, facility) -> Allocation

    Returns a list of dicts, one per (dtau, policy).
    """
    out = []
    for dt in dtaus:
        cohort = make_cohort(dt)
        lp = solve_lp(cohort, facility)
        _, dom = dominance_counts(cohort)
        adm = admissibility_counts(cohort)
        for name, fn in policies.items():
            rec = {'dtau': dt, 'policy': name,
                   'lambda_pt': lp.lam_pt, 'lambda_xt': lp.lam_xt}
            rec.update(summarise(cohort, fn(cohort, facility), facility))
            rec.update({'n_lp_dominated': dom['n_lp'],
                        'n_pareto_dominated': dom['n_pareto']})
            rec.update({k: adm[k] for k in
                        ('n_inadmissible', 'n_dntcp_le0', 'n_no_free_option')})
            out.append(rec)
    return out

def sweep_budget_xt(cohort, facility, fracs, policies = None):
    """Sweep the photon adaptation budget on the normalised axis.

    fracs are fractions of the cohort's photon adaptation demand, so 0 is the
    reference study's comparator and 1 is the free case by construction: the
    endpoints are tests T8 and T9. lambda_xt read at each point is the curve of
    road Section 5.12, output 2; absolute minutes are carried alongside as the
    secondary axis.

    policies, if given, are additionally evaluated at each point.

    Returns a list of dicts, one per point (per point and policy if policies
    are given).
    """
    demand = cohort.demand_xt()
    out = []
    for f in fracs:
        fac = Facility(facility.cap_pt_min_day, f * demand / facility.days,
                       facility.days)
        lp = solve_lp(cohort, fac)
        base = {'cxt_frac': f, 'cxt_min': fac.budget_xt,
                'lambda_pt': lp.lam_pt, 'lambda_xt': lp.lam_xt}
        if policies is None:
            out.append(base)
            continue
        for name, fn in policies.items():
            rec = dict(base)
            rec['policy'] = name
            rec.update(summarise(cohort, fn(cohort, fac), fac))
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
