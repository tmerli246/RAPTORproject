"""Synthetic cohorts for testing the allocator.

Coarse mode generates delta NTCP directly. This is enough to catch trivial
coding errors in the solver but does not exercise the NTCP layer or the
composition path.

At version 6 a patient holds two arms per modality per fractionation scheme,
non-adapted and adapted, and the number of blocks does not enter. `arm_cohort`
builds one scheme; `two_scheme_cohort` builds both, which is the only place a
non-concave benefit profile can now arise.

**Version 7.** Two changes, both structural, neither touching NTCP or
occupancy (allocator design 7.0, evaluator design 6.0; STATE.md Section 6).

XT-NA carries one fractionation schedule per patient rather than two, fixed
by a synthetic `hypo_frac` draw standing in for the clinical eligibility flag
of A32. `two_scheme_cohort` therefore emits **seven** strategies per patient
with the photon adapted arm present (`x_gain > 0`), not eight; `arm_cohort`,
holding one schedule only, is unaffected in count.

Every non-adapted strategy (XT-NA, PT-NA) now carries a synthetic
`block_plans` sequence, standing in for the coverage-screen outcome the
evaluator will produce once real imaging is available. Blocks fail
independently with a probability that decreases after each rescue; see
`_rescue_sequence`. This is metadata only: it does not feed into `ntcp` or
`occ_pt`/`occ_xt`, which are unaffected by whether a block was rescued,
because dose composition itself is out of scope until real patient data
arrives. Adapted strategies (PT-A, XT-A) carry the trivial all-planned
sequence, since their block plan is optimised on the anatomy it is evaluated
on and cannot fail by construction (A1, A4).

The failure probability and its decay are arbitrary placeholders (open
decision 27 confirmed the *mechanism*, unpriced and persistent rescue, not a
*rate*): p0 = 0.05, decay = 0.5, both keyword arguments so a real estimate
can replace them without touching call sites. n_blocks is likewise a
placeholder pending decision 23 for the hypofractionated schedule; the
default (3) matches the standard-schedule block count already used
elsewhere (STATE.md Section 7, test_threshold.py's N_STD = 30 at ten
fractions per block).
"""

import numpy as np

from tps5d.core.schema import Strategy, Cohort, BlockPlan

# Placeholders, all overridable per call. See the module docstring.
RESCUE_P0 = 0.05
RESCUE_DECAY = 0.5
N_BLOCKS = 3
HYPO_FRAC = 0.3

def _rescue_sequence(rng, n_blocks, p0, decay):
    """Which blocks of a non-adapted arm require rescue, and on what image.

    Block 0 is delivered on the planning anatomy and carries no modelled
    degradation (A23), so it is never rescued. From block 1, the plan
    currently in force fails independently with probability p0 * decay**k,
    k the number of rescues already incurred by this arm; decay in (0, 1]
    makes each further rescue less likely than the last, and decay = 1
    recovers a constant per-block probability. A failure generates a new
    rescue plan on that block's own image, which then becomes the plan in
    force for subsequent blocks until it fails in turn.

    Returns a list of BlockPlan of length n_blocks.
    """
    blocks = [BlockPlan(0, 'planned', 'pCT')]
    active_image, n_rescues = 'pCT', 0
    for b in range(1, n_blocks):
        p = p0 * (decay ** n_rescues)
        if rng.random() < p:
            active_image = f'rCT{b}'
            n_rescues += 1
            blocks.append(BlockPlan(b, 'rescue', active_image))
        else:
            blocks.append(BlockPlan(b, 'planned', active_image))
    return blocks

def _planned_sequence(n_blocks):
    """Trivial block sequence for an adapted arm: a fresh plan every block,
    none of them a rescue, since an adapted arm's plan is optimised on the
    anatomy it is then evaluated on (A1, A4)."""
    return [BlockPlan(0, 'planned', 'pCT')] + \
           [BlockPlan(b, 'planned', f'rCT{b}') for b in range(1, n_blocks)]

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

def _photon_baseline(pid, base, n_fx, scheme, rng, n_blocks, p_rescue0,
                     rescue_decay, tag = ''):
    """The patient's single XT-NA strategy, at the schedule clinical
    eligibility assigns it (A32). Reactively adapted at clinical margin: its
    block sequence carries whatever rescues the synthetic failure process
    draws, independently of every other arm's sequence.
    """
    bp = _rescue_sequence(rng, n_blocks, p_rescue0, rescue_decay)
    return Strategy(pid, f'xt{tag}', 'xt', n_fx = n_fx, tau_pt = 0.0,
                    ntcp = {'tot': base}, scheme = scheme, baseline = True,
                    block_plans = bp)

def _proton_and_adapted_photon(pid, base, tau0, dtau, n_fx, scheme, d_mod,
                               d_ada, rng, n_blocks, p_rescue0, rescue_decay,
                               x_gain = 0.0, dtau_xt = 0.0, tag = ''):
    """PT-NA, PT-A and, if x_gain > 0, XT-A, all under one schedule.

    Emitted for both schedules unconditionally: unlike XT-NA these three do
    not depend on clinical eligibility, only on capacity and benefit.

    d_mod  delta NTCP of non-adapted protons against the reference arm
    d_ada  additional delta NTCP bought by adapting, on either modality
    """
    pt_bp = _rescue_sequence(rng, n_blocks, p_rescue0, rescue_decay)
    out = [Strategy(pid, f'pt{tag}', 'pt', n_fx = n_fx, tau_pt = tau0,
                    ntcp = {'tot': base - d_mod}, scheme = scheme,
                    block_plans = pt_bp)]
    out.append(Strategy(pid, f'pta{tag}', 'pt', n_fx = n_fx, tau_pt = tau0 + dtau,
                        ntcp = {'tot': base - d_mod - d_ada}, scheme = scheme,
                        adapted = True, block_plans = _planned_sequence(n_blocks)))
    if x_gain > 0.0:
        out.append(Strategy(pid, f'xta{tag}', 'xt', n_fx = n_fx, tau_pt = 0.0,
                            tau_xt = dtau_xt, ntcp = {'tot': base - x_gain},
                            scheme = scheme, adapted = True,
                            block_plans = _planned_sequence(n_blocks)))
    return out

def arm_cohort(n = 8, tau0 = 30.0, dtau = 10.0, n_fx = 30, gain = 0.04,
               x_gain = 0.0, dtau_xt = 0.0, seed = 0,
               n_blocks = N_BLOCKS, p_rescue0 = RESCUE_P0,
               rescue_decay = RESCUE_DECAY):
    """Cohort on one fractionation scheme: four arms per patient at most.

    Each patient has the photon baseline XT-NA, then PT-NA and PT-A. With
    x_gain > 0 an XT-A arm is emitted as well, consuming the photon adaptation
    budget at dtau_xt minutes per fraction. With x_gain = 0 the cohort is the
    version 4 single-resource one.

    gain     per-patient scale of the proton adaptation benefit
    x_gain   per-patient scale of the photon adaptation benefit
    dtau_xt  extra photon linac minutes per fraction of an adapted arm
    n_blocks, p_rescue0, rescue_decay
             passed to _rescue_sequence for XT-NA and PT-NA; see the module
             docstring. There is one schedule here, so hypo_frac does not
             arise: XT-NA is simply the one patient carries

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
        out.append(_photon_baseline(pid, base, n_fx, 'std', rng, n_blocks,
                                    p_rescue0, rescue_decay))
        out += _proton_and_adapted_photon(
            pid, base, tau0, dtau, n_fx, 'std', d_mod[i], gain * scale[i],
            rng, n_blocks, p_rescue0, rescue_decay,
            x_gain = x_gain * scale_x[i] if x_gain > 0.0 else 0.0,
            dtau_xt = dtau_xt)
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
                      x_gain = 0.0, dtau_xt = 0.0, seed = 0,
                      hypo_frac = HYPO_FRAC,
                      n_blocks_std = N_BLOCKS, n_blocks_hyp = N_BLOCKS,
                      p_rescue0 = RESCUE_P0, rescue_decay = RESCUE_DECAY):
    """Cohort spanning both fractionation schemes: **seven** strategies per
    patient with the photon adapted arm present (x_gain > 0), five without.

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
    hypo_frac fraction of the cohort whose XT-NA is fixed to the
              hypofractionated schedule, standing in for the clinical
              eligibility flag of A32. An arbitrary placeholder pending the
              clinical partners' protocol criteria, not a modelling claim
    n_blocks_std, n_blocks_hyp, p_rescue0, rescue_decay
              passed to _rescue_sequence; see the module docstring

    Occupancy is the product of the fraction count and the session length, so
    the hypofractionated arms are much the cheaper even at tau_mult above one.
    Whether they are also the better is what `shape` controls.

    XT-NA is emitted once per patient, under whichever schedule hypo_frac
    assigns it (A32): version 6 emitted it under both schedules, which A27
    described as a patient holding two zero-cost options. That is retired.
    PT-NA, PT-A and, where x_gain > 0, XT-A are emitted under both schedules
    regardless, since only XT-NA's schedule is an exogenous clinical choice.
    """
    cfg = SHAPES[shape] if isinstance(shape, str) else shape
    pen, a_mult = cfg['pen'], cfg['a_mult']

    rng = np.random.default_rng(seed)
    scale = rng.uniform(0.5, 1.5, n)
    scale_x = rng.uniform(0.5, 1.5, n)
    d_mod = rng.uniform(0.01, 0.05, n)
    hypo_eligible = rng.random(n) < hypo_frac
    base = 0.30

    out = []
    for i in range(n):
        pid = f"p{i:02d}"
        xg = x_gain * scale_x[i] if x_gain > 0.0 else 0.0

        if hypo_eligible[i]:
            out.append(_photon_baseline(pid, base, n_hyp, 'hyp', rng,
                                        n_blocks_hyp, p_rescue0, rescue_decay,
                                        tag = 'h'))
        else:
            out.append(_photon_baseline(pid, base, n_std, 'std', rng,
                                        n_blocks_std, p_rescue0, rescue_decay,
                                        tag = ''))

        out += _proton_and_adapted_photon(
            pid, base, tau0, dtau, n_std, 'std', d_mod[i], gain * scale[i],
            rng, n_blocks_std, p_rescue0, rescue_decay,
            x_gain = xg, dtau_xt = dtau_xt, tag = '')
        out += _proton_and_adapted_photon(
            pid, base, tau0 * tau_mult, dtau, n_hyp, 'hyp',
            d_mod[i] - pen, gain * scale[i] * a_mult,
            rng, n_blocks_hyp, p_rescue0, rescue_decay,
            x_gain = xg, dtau_xt = dtau_xt, tag = 'h')
    return Cohort(out)
