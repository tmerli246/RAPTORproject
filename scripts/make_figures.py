"""Produce the allocator's figure set and results table.

When runs on a synthetic cohort, every figure carries the synthetic marker.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))

from tps5d.core.schema import Facility
from tps5d.allocator.policies import POLICIES
from tps5d.allocator import figures as fg
from tps5d.allocator.report import sweep, to_csv, dominance_counts

from synth import ladder_cohort

DTAUS = [2.4, 5.7, 9.3, 13.7, 19.0, 25.7]
FACILITY = Facility(cap_min_day = 480.0, days = 12)

def main(outdir = 'figures'):
    out = Path(outdir)
    out.mkdir(parents = True, exist_ok = True)
    fg.use_style()

    # Adaptation time changes occupancy, so the cohort is rebuilt at each point.
    make = lambda dt: ladder_cohort(n = 10, n_block = 2, dtau = dt, shape = 'concave', seed = 3)

    records = sweep(make, FACILITY, DTAUS, POLICIES)
    to_csv(records, out / 'policy_sweep.csv')

    fg.policy_curves(records, out / 'fig_policy_curves.pdf')
    fg.shadow_price(records, out / 'fig_shadow_price.pdf')
    fg.cohort_composition(records, policy = 'P3', path = out / 'fig_cohort_composition.pdf')

    cohort = make(13.7)
    fg.option_ladder(cohort, cohort.pids[0], path = out / 'fig_option_ladder.pdf')

    per_patient, tot = dominance_counts(cohort)
    print(f"options {tot['n_options']}, "
          f"Pareto dominated {tot['n_pareto']}, LP dominated {tot['n_lp']}")
    print(f"written to {out.resolve()}")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'figures')