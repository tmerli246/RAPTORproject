"""Two-scheme structural check.

The step-ratio threshold of the allocator document holds at a fixed
fractionation scheme: it compares photons, non-adapted protons and adapted
protons at one fraction count, which is why the fraction count cancels. With
two schemes in the strategy space a patient's options are no longer a single
chain but a family over (scheme, adaptation), and no single scalar summarises
the shape of its upper hull.

At version 6 adaptation is a binary property of the arm, so the family has four
proton members rather than 2(B + 1): non-adapted and adapted under each scheme.
This script asks a structural question: given a ratio of costs and benefits
between the two schemes, which (scheme, adaptation) pairs can survive the hull
at all? Options below the hull are never selected by the relaxation at any
capacity, so a pair that never survives is one the design need not carry.
The benefits here are parameters, chosen to span plausible ranges rather than
measured. The output is a map of reachable configurations against the two
quantities the study will measure.
"""

import numpy as np

from tps5d.allocator.dominance import hull

# Baseline setting, following the reference study for the standard schedule.
TAU0 = 34.2          # min per fraction, non-adapted session
N_STD = 30           # fractions, standard schedule (Section 9: three blocks of ten)
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

def ladder(dtau, pen, a_mult, tau_mult = TAU_MULT):
    """Option points for one patient across both schemes.

    dtau     extra minutes per adapted fraction
    pen      biological penalty of hypofractionation, in delta NTCP points,
             subtracted from the modality benefit of the hypo arm
    a_mult   ratio of adaptation benefit under hypofractionation to that under
             the standard schedule. Above one by the central hypothesis, since
             residual geometric error costs more when each fraction carries
             more dose

    Returns a list of (label, cost in minutes, benefit in delta NTCP points).
    """
    pts = [('xt', 0.0, 0.0)]
    arms = (('std', N_STD, TAU0, M_STD, A_STD),
            ('hyp', N_HYP, TAU0 * tau_mult, M_STD - pen, A_STD * a_mult))
    for tag, n_fx, tau0, m, a in arms:
        pts.append((f'{tag}NA', n_fx * tau0, m))
        pts.append((f'{tag}A', n_fx * (tau0 + dtau), m + a))
    return pts

def survivors(pts):
    """Labels surviving the upper convex hull, in increasing cost."""
    idx = hull([(c, u) for _, c, u in pts])
    return [pts[i][0] for i in idx]

def classify(labels):
    """Short description of the surviving configuration.

    Adaptation is binary at version 6, so the question is no longer whether
    intermediate counts survive but whether the non-adapted arm of a scheme
    survives alongside its adapted one. A scheme whose non-adapted arm is
    always below the hull is one for which the study can only report the
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
    print(__doc__.split('Run:')[0].strip()[:0] or '', end = '')

    print("Cost of one course, minutes")
    print(f"  standard, non-adapted   {N_STD * TAU0:8.0f}")
    print(f"  hypo, non-adapted       {N_HYP * TAU0 * TAU_MULT:8.0f}")
    print(f"  ratio                   {N_HYP * TAU_MULT / N_STD:8.2f}\n")

    print("Surviving options, by biological penalty and adaptation time")
    print("(pen = delta NTCP points lost by hypofractionation at fixed target effect)\n")
    dtaus = [5.0, 10.0, 19.0, 30.0]
    pens = [0.0, 2.0, 4.0, 6.0, 8.0]
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

    print("\nEffect of the central hypothesis: adaptation worth more under")
    print("hypofractionation (a_mult > 1), at pen = 4.0")
    print(f"{'a_mult':>7} " + " ".join(f"{'dtau ' + str(d):>26}" for d in dtaus))
    print("-" * (8 + 27 * len(dtaus)))
    for am in (1.0, 1.3, 1.6, 2.0):
        cells = [",".join(survivors(ladder(dt, 4.0, a_mult = am))) for dt in dtaus]
        print(f"{am:7.1f} " + " ".join(f"{c:>26}" for c in cells))

    print("\nPenalty at which the standard adapted arm re-enters the hull")
    print("At a_mult = 1 the two adapted arms differ only by pen, so at pen = 0")
    print("they carry equal utility and the cheaper one wins on a tie. The")
    print("threshold there is exactly zero and carries no information; the")
    print("informative sweep is over a_mult, where the hypofractionated arm")
    print("buys strictly more.")
    print(f"\n{'a_mult':>8}" + "".join(f"{'dtau ' + str(d):>16}" for d in dtaus))
    print("  " + "-" * (8 + 16 * len(dtaus)))
    for am in (1.0, 1.3, 1.6, 2.0):
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
