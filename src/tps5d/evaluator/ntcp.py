"""Biological functions for the evaluator.

Pure functions only: no model records and no model dictionary. Endpoint models
and their parameters live in the registry, which is the single place a
parameter is written down. Keeping both here and there invites a parameter to
be changed in one and not the other, so that a result depends on which module
was imported.
"""

import numpy as np
from scipy.stats import norm

# Biological conversion
# The course is composed of blocks that may differ in dose per fraction, and
# the evaluator's accumulation ordering is: BED per block on its own geometry,
# deform, sum over blocks, convert the total to EQD2 once. BED is additive over
# segments because the LQ model is multiplicative in survival; EQD2 is not.
def bed(dose, n_fx, ab):
    """Biologically effective dose of one segment, voxel-wise.
    dose : total physical dose of the segment (Gy)
    n_fx : number of fractions in the segment
    ab   : alpha/beta (Gy)
    """
    dose = np.clip(dose, 0.0, None)
    d = dose / n_fx
    return dose * (1.0 + d / ab)

def eqd2_from_bed(bed_total, ab):
    """Convert an accumulated BED field to EQD2."""
    return np.asarray(bed_total) / (1.0 + 2.0 / ab)

def eqd2(dose, n_fx, ab):
    """EQD2 of a single uniform-fractionation course, voxel-wise.
    Convenience wrapper for the one-segment case; multi-block courses go
    through bed() and eqd2_from_bed().
    """
    return eqd2_from_bed(bed(dose, n_fx, ab), ab)

# Dose reduction
# The cache boundary is the DVH: TD50 and m enter only at the final evaluation,
# but the volume parameter n enters through the gEUD exponent, so a cached gEUD
# cannot be re-evaluated at a perturbed n while a cached DVH can.
#
# The DVH itself comes from OpenTPS (opentps.core.data.DVH), which computes it
# from a DoseImage and an ROIMask and exposes it through `histogram` as a
# cumulative curve: dose bin centres in Gy and the volume receiving at least
# that dose, in per cent. We do not compute our own.
#
# NB: OpenTPS writes the power-mean exponent as EUDa in its
# optimisation objectives, where we write 1/n with n the LKB volume parameter.
# EUDa = 1/n. 
def geud(dose, n):
    """Generalized equivalent uniform dose from equal-volume voxel doses.
    dose : voxel doses (Gy)
    n    : LKB volume parameter
    """
    dose = np.clip(dose, 0.0, None)
    return np.mean(dose ** (1.0 / n)) ** n

def geud_from_cumulative_dvh(dose_bins, volume_pct, n):
    """gEUD from a cumulative DVH, as returned by OpenTPS DVH.histogram.

    dose_bins  : bin centres (Gy), increasing
    volume_pct : volume receiving at least that dose (per cent), decreasing
    n          : LKB volume parameter

    The power mean needs volume fractions per bin, so the cumulative curve is
    differenced first. Recomputing gEUD at a perturbed n costs one pass over a
    few thousand bins, which is what makes the parameter propagation affordable
    without touching the accumulated dose field.

    Binning error against the voxel-wise route is assumption E3, verified once
    on a real case rather than assumed.
    """
    dose_bins = np.asarray(dose_bins, dtype = float)
    volume_pct = np.asarray(volume_pct, dtype = float)
    frac = -np.diff(volume_pct, append = 0.0) / 100.0
    frac = np.clip(frac, 0.0, None)
    total = frac.sum()
    if total <= 0.0:
        raise ValueError("empty DVH: no volume in any bin")
    frac = frac / total
    return float(np.sum(frac * np.clip(dose_bins, 0.0, None) ** (1.0 / n)) ** n)

# NTCP
# The probit step is separate from the dose reduction so that the Monte Carlo
# parameter propagation can loop over (td50, m) at a fixed gEUD, and over n at
# a fixed DVH, without touching any dose array.
def lkb_from_geud(g, td50, m):
    """LKB probit on a precomputed gEUD. Vectorized over parameters."""
    t = (g - td50) / (m * td50)
    return norm.cdf(t)