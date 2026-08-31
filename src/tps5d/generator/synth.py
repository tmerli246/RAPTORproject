"""Synthetic cohorts for testing the allocator.

Coarse mode generates delta NTCP directly. This is enough to catch trivial
coding errors in the solver but does not exercise the NTCP layer or the
composition path.

At version 6 a patient holds two arms per modality per fractionation scheme,
non-adapted and adapted, and the number of blocks does not enter. `arm_cohort`
builds one scheme; `two_scheme_cohort` builds both, which is the only place a
non-concave benefit profile can now arise.
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
                            ntcp = {'tot': base - dntcp[i]}, adapted = True))
    return Cohort(out)

# Deprecated alias: the original name misspelled Borderias-Villarroel.
Villaroel_cohort = villarroel_cohort

def _arms(pid, base, tau0, dtau, n_fx, scheme, d_mod, d_ada,
          x_gain = 0.0, dtau_xt = 0.0, baseline = False, tag = ''):
    """The arms of one patient under one fractionation scheme.

    XT-NA is emitted with `baseline` set only once per patient, so that a
    two-scheme cohort carries one locked reference arm rather than two. The
    free photon arm of the second scheme is emitted as a non-baseline zero-cost
    option, which is the situation A27 describes.

    d_mod  delta NTCP of non-adapted protons against the reference arm
    d_ada  additional delta NTCP bought by adapting, on either modality
    """
    out = [Strategy(pid, f'xt{tag}', 'xt', n_fx = n_fx, tau_pt = 0.0,
                    ntcp = {'tot': base}, scheme = scheme, baseline = baseline)]
    out.append(Strategy(pid, f'pt{tag}', 'pt', n_fx = n_fx, tau_pt = tau0,
                        ntcp = {'tot': base - d_mod}, scheme = scheme))
    out.append(Strategy(pid, f'pta{tag}', 'pt', n_fx = n_fx, tau_pt = tau0 + dtau,
                        ntcp = {'tot': base - d_mod - d_ada}, scheme = scheme,
                        adapted = True))
    if x_gain > 0.0:
        out.append(Strategy(pid, f'xta{tag}', 'xt', n_fx = n_fx, tau_pt = 0.0,
                            tau_xt = dtau_xt, ntcp = {'tot': base - x_gain},
                            scheme = scheme, adapted = True))
    return out

def arm_cohort(n = 8, tau0 = 30.0, dtau = 10.0, n_fx = 30, gain = 0.04,
               x_gain = 0.0, dtau_xt = 0.0, seed = 0):
    """Cohort on one fractionation scheme: four arms per patient at most.

    Each patient has the photon baseline XT-NA, then PT-NA and PT-A. With
    x_gain > 0 an XT-A arm is emitted as well, consuming the photon adaptation
    budget at dtau_xt minutes per fraction. With x_gain = 0 the cohort is the
    version 4 single-resource one.

    gain     per-patient scale of the proton adaptation benefit
    x_gain   per-patient scale of the photon adaptation benefit
    dtau_xt  extra photon linac minutes per fraction of an adapted arm

    The proton chain has three points, so its hull is either concave or has one
    interior point below it. A richer benefit profile requires two schemes; see
    two_scheme_cohort.
    """
    rng = np.random.default_rng(seed)
    scale = rng.uniform(0.5, 1.5, n)
    scale_x = rng.uniform(0.5, 1.5, n)
    d_mod = rng.uniform(0.01, 0.05, n)      # benefit of protons before adaptation
    base = 0.30

    out = []
    for i in range(n):
        pid = f"p{i:02d}"
        out += _arms(pid, base, tau0, dtau, n_fx, 'std',
                     d_mod[i], gain * scale[i],
                     x_gain = x_gain * scale_x[i] if x_gain > 0.0 else 0.0,
                     dtau_xt = dtau_xt, baseline = True)
    return Cohort(out)

# Configurations of the two-scheme proton frontier, named by what the hull does
# to it.
#
# pen     biological penalty of hypofractionation, in delta NTCP, applied to
#         the modality benefit of the hypofractionated arms
# a_mult  ratio of adaptation benefit under hypofractionation to that under the
#         standard schedule. Above one by the central hypothesis, since
#         residual geometric error costs more when each fraction carries more
#         dose
# The standard non-adapted proton arm is below the hull in every reachable
# configuration. This is not a choice of parameters: under the per-fraction
# adaptation charge of A16 the adapted hypofractionated arm costs a fifth of the
# standard non-adapted one, so it is both cheaper and better unless the
# biological penalty is large. The cost asymmetry the allocator design records
# as favouring hypofractionation by n over B appears here mechanically.
SHAPES = {
    'both_schemes': dict(pen = 0.000, a_mult = 0.2),   # four rungs on the hull
    'nonconcave':   dict(pen = 0.020, a_mult = 0.6),   # three, one rung below
    'hyp_dominant': dict(pen = 0.010, a_mult = 2.5),   # two, no standard arm
}

def two_scheme_cohort(n = 8, shape = 'both_schemes', tau0 = 30.0, dtau = 10.0,
                      n_std = 30, n_hyp = 5, tau_mult = 1.5, gain = 0.04,
                      x_gain = 0.0, dtau_xt = 0.0, seed = 0):
    """Cohort spanning both fractionation schemes: eight arms per patient.

    This is where a non-concave benefit profile now comes from. At version 5 it
    came from the curvature of the benefit in the adaptation count; with two
    arms per scheme that curvature does not exist, and the shape of a patient's
    proton frontier is set instead by where the hypofractionated arms fall
    relative to the standard ones.

    shape     key of SHAPES, or a dict carrying 'pen' and 'a_mult'
    n_std     fractions on the standard schedule
    n_hyp     fractions on the hypofractionated schedule
    tau_mult  session-length multiplier under hypofractionation. Above one,
              through higher MU, but sub-linear in dose per fraction

    Occupancy is the product of the fraction count and the session length, so
    the hypofractionated arms are much the cheaper even at tau_mult above one.
    Whether they are also the better is what `shape` controls.
    """
    cfg = SHAPES[shape] if isinstance(shape, str) else shape
    pen, a_mult = cfg['pen'], cfg['a_mult']

    rng = np.random.default_rng(seed)
    scale = rng.uniform(0.5, 1.5, n)
    scale_x = rng.uniform(0.5, 1.5, n)
    d_mod = rng.uniform(0.01, 0.05, n)
    base = 0.30

    out = []
    for i in range(n):
        pid = f"p{i:02d}"
        xg = x_gain * scale_x[i] if x_gain > 0.0 else 0.0
        out += _arms(pid, base, tau0, dtau, n_std, 'std',
                     d_mod[i], gain * scale[i],
                     x_gain = xg, dtau_xt = dtau_xt, baseline = True, tag = '')
        out += _arms(pid, base, tau0 * tau_mult, dtau, n_hyp, 'hyp',
                     d_mod[i] - pen, gain * scale[i] * a_mult,
                     x_gain = xg, dtau_xt = dtau_xt, baseline = False, tag = 'h')
    return Cohort(out)
