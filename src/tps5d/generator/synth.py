"""Synthetic cohorts for testing the allocator.

Coarse mode generates delta NTCP directly. This is enough to catch trivial
coding errors in the solver but does not exercise the NTCP layer or the
composition path.
"""

import numpy as np

from tps5d.core.schema import Strategy, Cohort

def villarroel_cohort(n = 14, extra = 0.0, tau0 = 34.2, dntcp = None, seed = 0):
    """Cohort with the structure of the reference study.
    Two options per patient: the locked photon baseline, and a single adapted
    proton strategy whose occupancy is the same for every patient.

    n      number of patients
    extra  additional minutes per fraction required by adaptation
    tau0   baseline session length, minutes
    dntcp  per-patient benefit of the proton strategy. Random if omitted
    """
    rng = np.random.default_rng(seed)
    if dntcp is None:
        dntcp = rng.uniform(0.02, 0.12, n)
    dntcp = np.asarray(dntcp, dtype = float)

    base = 0.30
    out = []
    for i in range(n):
        pid = f"p{i:02d}"
        out.append(Strategy(pid, 'xt', 'xt', n_fx = 1, tau_pt = 0.0,
                            ntcp = {'tot': base}, baseline = True))
        out.append(Strategy(pid, 'pt', 'pt', n_fx = 1, tau_pt = tau0 + extra,
                            ntcp = {'tot': base - dntcp[i]}, n_adapt = 1))
    return Cohort(out)

# Deprecated alias: the original name misspelled Borderias-Villarroel.
Villaroel_cohort = villarroel_cohort

def _shape(f, shape):
    if shape == 'concave':
        return np.sqrt(f)
    if shape == 'convex':
        return f ** 2
    return f

def ladder_cohort(n = 8, n_block = 2, tau0 = 30.0, dtau = 10.0, n_fx = 30,
                  gain = 0.04, shape = 'concave', x_gain = 0.0, dtau_xt = 0.0,
                  seed = 0):
    """Cohort with a per-patient ladder of adaptation counts.

    Each patient has a photon baseline, then proton strategies with 0, 1, ...,
    n_block adapted blocks. Occupancy depends only on the adaptation count.
    With x_gain > 0, a photon chain is emitted as well: XT-A strategies with
    1, ..., n_block adapted blocks, consuming the photon adaptation budget at
    dtau_xt extra minutes per adapted fraction. With x_gain = 0 the cohort is
    exactly the version 4 single-resource one.

    gain     per-patient scale of the proton adaptation benefit
    shape    'concave', 'linear' or 'convex' in the adaptation count. Controls
             whether greedy allocation is expected to be safe. Applies to both
             chains
    x_gain   per-patient scale of the photon adaptation benefit
    dtau_xt  extra photon linac minutes per adapted fraction
    """
    rng = np.random.default_rng(seed)
    scale = rng.uniform(0.5, 1.5, n)
    base = 0.30
    d_mod = rng.uniform(0.01, 0.05, n)      # benefit of protons before adaptation
    scale_x = rng.uniform(0.5, 1.5, n)

    out = []
    for i in range(n):
        pid = f"p{i:02d}"
        out.append(Strategy(pid, 'xt', 'xt', n_fx = n_fx, tau_pt = 0.0,
                            ntcp = {'tot': base}, baseline = True))
        for k in range(n_block + 1):
            f = k / n_block if n_block else 0.0
            d = d_mod[i] + gain * scale[i] * _shape(f, shape)
            out.append(Strategy(pid, f'pt{k}', 'pt', n_fx = n_fx,
                                tau_pt = tau0 + dtau * k / n_block if n_block else tau0,
                                ntcp = {'tot': base - d}, n_adapt = k))
        if x_gain > 0.0:
            for j in range(1, n_block + 1):
                f = j / n_block
                d = x_gain * scale_x[i] * _shape(f, shape)
                out.append(Strategy(pid, f'xt{j}', 'xt', n_fx = n_fx,
                                    tau_pt = 0.0, tau_xt = dtau_xt * j / n_block,
                                    ntcp = {'tot': base - d}, n_adapt = j))
    return Cohort(out)
