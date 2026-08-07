"""Step ratio: is a patient's option ladder concave from the origin?

The allocator drops options lying below the upper convex hull of a patient's
(cost, benefit) points. Whether the intermediate adaptation counts survive that
reduction, and therefore whether per-block adaptation is a live decision at all,
depends on how the modality step compares with the adaptation steps in benefit
per machine-minute.

    rho = (benefit per minute of the modality step)
        / (benefit per minute of the first adaptation step)

    rho >= 1   the ladder is concave at the bottom, intermediate adaptation
               counts can survive, per-block allocation is meaningful
    rho <  1   the ladder is convex at the bottom, the hull keeps only photons
               and full adaptation, and the problem collapses to the reference
               study's structure

Inputs are taken from Borderias-Villarroel et al. 2024. They are lung data with
mean-dose logistic endpoints and do not transfer to abdomen or pelvis. The point
of the calculation is the order of magnitude and the sign, not the value.

Margin is not an independent component of the strategy. Setup error is reduced
only where the plan is made on that block's repeat CT, so a reduced-margin plan
cannot be delivered in a non-adapted block. The adaptation step therefore
carries the benefit of adaptation *and* of margin reduction together, which is
the OAPT-2mm column of the reference study rather than the OAPT-Clinic one. The
clinical-margin figures are retained below only as the control case, in which
adaptation is performed at an unchanged uncertainty budget.
"""

import numpy as np

# Reference study. Baseline session length, fraction count, and the extra
# minutes per adapted fraction, which the study sweeps from 2.4 to 25.7.
TAU0 = 34.2
N_FX = 30

# Delta NTCP against the non-adaptive photon reference, per cent.
# m  modality step, XT to non-adapted PT
# a  adaptation step at ideal (instantaneous) adaptation, on top of m
GAINS = {
    #                        m     a_clinic   a_2mm
    '2-year mortality':    (6.9,      0.9,      3.8),
    'dysphagia':           (6.1,     None,      7.5),
    'pneumonitis':         (7.7,     None,      4.7),
}


def rho(m, a_total, dtau, n_block=2, p=1.0, tau0=TAU0, n_fx=N_FX):
    """Ratio of modality efficiency to first-adaptation efficiency.

    m        delta NTCP of the modality step
    a_total  delta NTCP of adapting every block
    dtau     extra minutes per adapted fraction
    n_block  number of adaptation blocks
    p        concavity of the adaptation benefit in the block count,
             a(k) = a_total * (k / n_block) ** p. p = 1 linear, p < 1 concave
    """
    eff_mod = m / (n_fx * tau0)
    a_first = a_total * (1.0 / n_block) ** p
    eff_ada = a_first / (n_fx * dtau / n_block)
    return eff_mod / eff_ada


def dtau_star(m, a_total, n_block=2, p=1.0, tau0=TAU0):
    """Extra minutes per fraction at which rho crosses one."""
    a_first = a_total * (1.0 / n_block) ** p
    return tau0 * a_first * n_block / m


# Reported adaptation times, for reference. PSI measured just under 7 min for
# the adaptation part of a clinical daily adaptive proton session; McComas
# reported about 16 additional minutes per adaptive pelvic photon fraction.
DTAU = [2.4, 5.7, 7.0, 9.3, 13.7, 16.0, 19.0, 25.7]

def hull_size(m, a_total, dtau, n_block=2, p=1.0, tau0=TAU0, n_fx=N_FX):
    """How many options survive the hull, photon included.

    Two means the ladder has collapsed to photons and full adaptation, so the
    per-block adaptation decision carries no value for that patient.
    """
    from tps5d.allocator.dominance import hull as upper_hull

    pts = [(0.0, 0.0)]
    for k in range(n_block + 1):
        cost = n_fx * tau0 + (k / n_block) * n_fx * dtau
        gain = m + a_total * (k / n_block) ** p
        pts.append((cost, gain))
    return len(upper_hull(pts))


if __name__ == '__main__':
    print("\nCASO REALE: la riduzione di margine segue l'adattamento blocco per blocco")
    print("rho e numero di opzioni superstiti, 2 blocchi, beneficio lineare\n")
    print(f"{'dtau':>6}   " + "   ".join(f"{k:>18}" for k in
                                         ['2ym', 'disfagia', 'polmonite']))
    print("-" * 70)
    for dt in DTAU:
        cells = []
        for m, a in [(6.9, 3.8), (6.1, 7.5), (7.7, 4.7)]:
            cells.append(f"rho {rho(m, a, dt):5.2f}  opz {hull_size(m, a, dt)}")
        print(f"{dt:6.1f}   " + "   ".join(f"{c:>18}" for c in cells))

    print("\nCONTROLLO: adattamento a margini invariati (arm PT-A margine 1)")
    print(f"{'dtau':>6}   {'2ym':>18}")
    print("-" * 30)
    for dt in DTAU:
        print(f"{dt:6.1f}   rho {rho(6.9, 0.9, dt):5.2f}  opz {hull_size(6.9, 0.9, dt)}")

    print("\nSoglia dtau* alla quale rho = 1 (minuti extra per frazione)")
    print(f"{'arm':>28} {'p = 1':>8} {'p = 0.5':>9}")
    print("-" * 48)
    for name, (m, a_c, a_2) in GAINS.items():
        print(f"{name + ', margine ridotto':>28} "
              f"{dtau_star(m, a_2):8.1f} {dtau_star(m, a_2, p=0.5):9.1f}")
    print(f"{'2ym, controllo margine fisso':>28} "
          f"{dtau_star(6.9, 0.9):8.1f} {dtau_star(6.9, 0.9, p=0.5):9.1f}")
