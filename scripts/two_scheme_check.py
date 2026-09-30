"""Two-scheme structural check.

Run from the repository root, with the package importable:

    python scripts/two_scheme_check.py

The step-ratio threshold of the allocator document holds at a fixed
fractionation scheme: it compares photons, non-adapted protons and adapted
protons at one fraction count, which is why the fraction count cancels. With
two schemes in the strategy space a patient's options are no longer a single
chain but a family over (scheme, adaptation), and no single scalar summarises
the shape of its upper hull.

Adaptation is a binary property of the arm, so the family has four proton
members: non-adapted and adapted under each scheme. This script asks a
structural question: given a ratio of costs and benefits between the two
schemes, which (scheme, adaptation) pairs lie on the upper hull? The benefits
are parameters, chosen to span plausible ranges rather than measured. The
output is a map of hull membership against the two quantities the study will
measure.

What the map is. Options below the hull are never selected by the relaxation
and so never enter the shadow prices. The integer optimum can select them, so
an arm that is off the hull still belongs in the option set. Only
Pareto-dominated arms can be omitted for both problems. This is therefore a map
of the linear relaxation. It covers the proton family only: there is no XT-A, so
the photon outside option of allocator 6.2 is zero (the C_XT = 0 slice), and one
(m, a) pair stands for every patient, whereas the thresholds are patient-wise.
"""

import numpy as np

from tps5d.allocator.dominance import hull

# Baseline setting, following the reference study for the standard schedule.
TAU0 = 34.2          # min per fraction, non-adapted session
N_STD = 30           # fractions, standard schedule (reference study; allocator 2, A23)
N_HYP = 5            # fractions, hypofractionated schedule

# Delivery time per fraction is longer under hypofractionation, through higher
# MU, but sub-linearly in dose per fraction: a fivefold dose per fraction does
# not give a fivefold session. The multiplier is a parameter, not a measurement.
TAU_MULT = 1.5

# Modality benefit, delta NTCP of non-adapted protons against the photon
# baseline. Order of magnitude from the reference study's lung values.
M_STD = 6.9

# Adaptation benefit at full adaptation, together with the margin reduction it
# licenses, on the standard schedule.
A_STD = 3.8

def ladder(dtau, pen, a_mult, tau_mult = TAU_MULT, tau0 = TAU0, n_std = N_STD,
           n_hyp = N_HYP, m = M_STD, a = A_STD):
    """Option points for one patient across both schemes.

    dtau     extra minutes per adapted fraction
    pen      biological penalty of hypofractionation, in delta NTCP points,
             subtracted from the modality benefit of the hypo arm
    a_mult   ratio of adaptation benefit under hypofractionation to that under
             the standard schedule. An assumption of the parametrisation:
             adaptation is worth more when each fraction carries more dose.
             Road 3.4 lists this mechanism as not modelled
    m, a     modality and adaptation benefit on the standard schedule, in
             delta NTCP points

    Returns a list of (label, cost in minutes, benefit in delta NTCP points).
    """
    pts = [('xt', 0.0, 0.0)]
    arms = (('std', n_std, tau0, m, a),
            ('hyp', n_hyp, tau0 * tau_mult, m - pen, a * a_mult))
    for tag, n_fx, tau, mod, ada in arms:
        pts.append((f'{tag}NA', n_fx * tau, mod))
        pts.append((f'{tag}A', n_fx * (tau + dtau), mod + ada))
    return pts

def survivors(pts):
    """Labels on the upper convex hull, in increasing cost."""
    idx = hull([(c, u) for _, c, u in pts])
    return [pts[i][0] for i in idx]

def classify(labels):
    """Short description of the configuration on the hull.

    Adaptation is binary, so the question is whether the non-adapted arm of a
    scheme is on the hull alongside its adapted one. A scheme whose non-adapted
    arm is always below the hull is one for which the study can only report the
    adapted workflow.
    """
    arms = {l[:3] for l in labels if l != 'xt'}
    if not arms:
        return 'photons only'
    na = {l[:3] for l in labels if l.endswith('NA')}
    both = 'std' in arms and 'hyp' in arms
    if both:
        live = ",".join(sorted(na))
        return f'both schemes, non-adapted live: {live}' if live \
               else 'both schemes, adapted only'
    one = arms.pop()
    return f'{one} only, non-adapted live' if one in na else f'{one} only, adapted only'

if __name__ == '__main__':
    print("Cost of one course, minutes")
    print(f"  standard, non-adapted   {N_STD * TAU0:8.0f}")
    print(f"  hypo, non-adapted       {N_HYP * TAU0 * TAU_MULT:8.0f}")
    print(f"  ratio                   {N_HYP * TAU_MULT / N_STD:8.2f}\n")

    print("Map of the upper hull, the linear relaxation, proton family only.")
    print("Off-hull arms can still be selected by the integer optimum.\n")

    print("Arms on the hull, by biological penalty and adaptation time")
    print("(pen = delta NTCP points lost by hypofractionation at fixed target effect;")
    print("pen = 0 is a tie between the adapted arms at a_mult = 1, see the last block)\n")
    dtaus = [5.0, 10.0, 19.0, 30.0]
    pens = [0.5, 2.0, 4.0, 6.0, 8.0]
    print(f"{'pen':>5} " + " ".join(f"{'dtau ' + str(d):>26}" for d in dtaus))
    print("-" * (6 + 27 * len(dtaus)))
    for pen in pens:
        cells = []
        for dt in dtaus:
            s = survivors(ladder(dt, pen, a_mult = 1.0))
            cells.append(",".join(s))
        print(f"{pen:5.1f} " + " ".join(f"{c:>26}" for c in cells))

    print("\nConfiguration reached, same sweep")
    print(f"{'pen':>5} " + " ".join(f"{'dtau ' + str(d):>34}" for d in dtaus))
    print("-" * (6 + 35 * len(dtaus)))
    for pen in pens:
        cells = [classify(survivors(ladder(dt, pen, a_mult = 1.0))) for dt in dtaus]
        print(f"{pen:5.1f} " + " ".join(f"{c:>34}" for c in cells))

    a_mults = (0.2, 0.6, 1.0, 1.3, 1.6, 2.0)

    print("\nEffect of a_mult, adaptation worth more (above one) or less (below one)")
    print("under hypofractionation, at pen = 2.0. The standard adapted arm leaves the")
    print("hull where pen < pen* = a (a_mult - 1)")
    print(f"{'a_mult':>7} " + " ".join(f"{'dtau ' + str(d):>26}" for d in dtaus))
    print("-" * (8 + 27 * len(dtaus)))
    for am in a_mults:
        cells = [",".join(survivors(ladder(dt, 2.0, a_mult = am))) for dt in dtaus]
        print(f"{am:7.1f} " + " ".join(f"{c:>26}" for c in cells))

    print("\nPenalty at which the standard adapted arm reaches the hull")
    print("At a_mult = 1 the two adapted arms differ only by pen, so at pen = 0")
    print("they carry equal utility and the cheaper one wins on a tie. The")
    print("threshold there is exactly zero and carries no information; the")
    print("informative sweep is over a_mult, where the hypofractionated arm")
    print("buys strictly more or less.")
    print(f"\n{'a_mult':>8}" + "".join(f"{'dtau ' + str(d):>16}" for d in dtaus))
    print("  " + "-" * (8 + 16 * len(dtaus)))
    for am in a_mults:
        row = f"{am:8.1f}"
        for dt in dtaus:
            has = lambda p: any(l.startswith('std')
                                for l in survivors(ladder(dt, p, am)))
            if has(0.0):
                row += f"{'0 (unpenalised)':>16}"
            elif not has(9.0):
                row += f"{'> 9.0':>16}"
            else:
                lo, hi = 0.0, 9.0
                for _ in range(40):
                    mid = 0.5 * (lo + hi)
                    lo, hi = (lo, mid) if has(mid) else (mid, hi)
                row += (f"{'0+':>16}" if hi < 1e-6 else f"{hi:16.2f}")
        print(row)
    print("\n0+ means any strictly positive penalty suffices: the arms are tied")
    print("at pen = 0 and the cheaper one is kept only by the tie-break.")
    print("0 (unpenalised) means the standard adapted arm is on the hull at pen = 0,")
    print("as it is wherever pen* is negative (a_mult below one).")
