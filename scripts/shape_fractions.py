"""Composition of the proton hull for the three benefit shapes of the generator.

Run from the repository root, with the package importable:

    python scripts/shape_fractions.py

For each shape of `synth.SHAPES` and each proton adaptation time of the
reference-study sweep, the percentage of generated patients whose proton chain
holds each proton arm on its upper convex hull. The chain is XT-NA and the four
proton arms on the proton cost axis (`dominance.ladders`). These are the
percentages quoted in allocator design 5.5.

They describe the generator. Every benefit and cost it draws is illustrative,
and none of the percentages is an estimate for the study cohort.
"""

from tps5d.allocator.dominance import ladders
from tps5d.generator.synth import SHAPES, two_scheme_cohort

DTAUS = [2.4, 5.7, 9.3, 13.7, 19.0, 25.7]   # reference study, allocator 2
N_PATIENTS = 400
SEED = 11
X_GAIN = 0.03        # any positive value: the photon arm is off the proton chain
DTAU_XT = 16.0       # must be positive, for the same reason
ARMS = ['PT-NA std', 'PT-NA hyp', 'PT-A std', 'PT-A hyp']   # arm label and scheme

def on_hull(shape, dtau):
    """Percentage of patients with each proton arm on the hull."""
    cohort = two_scheme_cohort(n = N_PATIENTS, shape = shape, dtau = dtau, x_gain = X_GAIN,
                               dtau_xt = DTAU_XT, seed = SEED)
    kept, _ = ladders(cohort)
    count = dict.fromkeys(ARMS, 0)
    for rungs in kept.values():
        for s in rungs:
            label = f"{s.arm} {s.scheme}"
            if label in count:
                count[label] += 1
    return {a: 100.0 * count[a] / len(kept) for a in ARMS}

if __name__ == '__main__':
    print(f"{N_PATIENTS} generated patients, seed {SEED}, per cent with the arm on the hull")
    print(f"{'shape':<14}{'dtau':>6}" + ''.join(f"{a:>11}" for a in ARMS))
    for shape in SHAPES:
        for dtau in DTAUS:
            pct = on_hull(shape, dtau)
            print(f"{shape:<14}{dtau:6.1f}" + ''.join(f"{pct[a]:11.1f}" for a in ARMS))
