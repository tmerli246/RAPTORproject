"""Dose composition: BED per block, warping, summation, EQD2, DVH, gEUD.

Evaluator design 4, 5 and 7.1 specify this machinery; this module turns the
specification into functions, evaluator design 11. Each function is the
array operation one row of those sections names, and nothing more:
evaluator/ntcp.py and evaluator/registry.py are not touched here, since this
module's output is a DVH, the cache boundary evaluator 7.1 already draws.

Geometry-preserving throughout: every function that transforms an
Image3D-family object (DoseImage or a plain BED/EQD2 field of the same
family) uses that object's own `.copy()` rather than constructing a new one
by hand, since `.copy()` is what DoseImage, ROIMask and CTImage override to
preserve subclass type and deep-copy the array (extractor design 3.2, X1),
and the base Image3D.copy() does neither.
"""

import numpy as np

from opentps.core.data import DVH


def compute_bed(dose_per_fraction, n_fx: int, alpha_beta: float):
    """BED_b(x) = n_b . d_b(x) . (1 + d_b(x)/(alpha/beta)), evaluator design 4.1.

    d_b(x) here is `dose_per_fraction`'s own array directly: evaluator
    design 4.1 defines d_b(x) = D_b(x)/n_b, and extractor design 5 already
    stores physical dose per fraction, so D_b(x)/n_b is exactly what is
    passed in. Confirmed against the formula's own definition, not assumed
    because it is convenient (evaluator design 11.1).

    Parameters
    ----------
    dose_per_fraction : DoseImage
        On the block's own native geometry, per extractor design 5:
        conversion precedes deformation, never the reverse.
    n_fx : int
        This block's fraction count.
    alpha_beta : float
        Gy, for the ROI this BED field is being computed for. BED_b depends
        on it, so one field exists per (block, scheme, alpha/beta), per
        evaluator design 4.3.

    Returns
    -------
    Same type as `dose_per_fraction`, same geometry, BED values.
    """
    d = dose_per_fraction.imageArray
    bed = n_fx * d * (1.0 + d / alpha_beta)

    result = dose_per_fraction.copy()
    result._imageArray = bed.astype(np.float32)
    return result


def warp_bed(bed_field, dvf):
    """Apply an already-computed deformation field to a BED field.

    Takes `dvf` as given rather than calling extractor.adapters.get_dvf
    itself: registration is expensive and is performed once per image pair
    and cached (extractor design 6, evaluator design 4.3); applying a
    cached field to an array is cheap and is repeated once per (block,
    scheme, alpha/beta) combination. Keeping the two separate here is what
    makes evaluator design 4.3's "four applications, not four
    registrations" true in the code, not only in the design document.

    Parameters
    ----------
    bed_field : DoseImage-family object
        On the block's native geometry, as returned by compute_bed.
    dvf : Deformation3D
        fixed = pCT, moving = the block's repeat image, per extractor
        design 6.2 and X3. Already resampled onto the working grid, per
        extractor design 6.1: this function does not resample and does not
        check that it was done, since that is get_dvf's contract, not this
        function's.

    Returns
    -------
    Same type as `bed_field`, on `dvf`'s fixed grid.
    """
    return dvf.deformImage(bed_field)


def sum_bed(bed_fields: list):
    """Sum warped BED fields into one accumulated field, evaluator design 5.1.

    BED is additive over segments because the underlying model is
    multiplicative in survival (evaluator design 4.1); summation after
    deformation is therefore exact, not an approximation. All fields must
    already be on the same grid, since they were all warped onto the same
    fixed image by warp_bed; this is checked rather than assumed, the same
    discipline extractor design 5's union_bounding_box applies to masks.

    Parameters
    ----------
    bed_fields : list of DoseImage-family objects, same type, same grid.

    Returns
    -------
    Same type as the inputs, same grid, summed values.
    """
    if not bed_fields:
        raise ValueError("sum_bed: no fields given")

    ref = bed_fields[0]
    ref_shape = ref.imageArray.shape
    for f in bed_fields[1:]:
        if f.imageArray.shape != ref_shape:
            raise ValueError(
                f"sum_bed: fields do not share a grid: {ref_shape} vs "
                f"{f.imageArray.shape}. Every field must already be warped "
                f"onto the same fixed image by warp_bed before summation."
            )
        if not np.allclose(f.origin, ref.origin) or not np.allclose(f.spacing, ref.spacing):
            raise ValueError(
                "sum_bed: fields share a shape but not an origin or "
                "spacing: same grid_size does not imply same grid."
            )

    total = np.zeros(ref_shape, dtype=np.float32)
    for f in bed_fields:
        total += f.imageArray

    result = ref.copy()
    result._imageArray = total
    return result


def bed_to_eqd2(bed_total, alpha_beta: float):
    """EQD2(x) = BED_total(x) / (1 + 2/(alpha/beta)), evaluator design 4.1.

    Applied once, to the summed field, never per block: converting before
    summation would be the ordering evaluator design 4.1 rejects, since the
    conversion is nonlinear and does not commute with the deformation
    already applied to each block. This function does not know or check
    that its input has already been summed; get that ordering right by
    construction of the call sequence, not by a check here that could
    itself be fooled by a single-block edge case.

    Returns
    -------
    Same type as `bed_total`, same geometry, EQD2 values.
    """
    bed = bed_total.imageArray
    eqd2 = bed / (1.0 + 2.0 / alpha_beta)

    result = bed_total.copy()
    result._imageArray = eqd2.astype(np.float32)
    return result


def reduce_to_dvh(eqd2_field, roi_mask, *, max_dvh: float = None):
    """DVH of an accumulated EQD2 field over one ROI, evaluator design 7.1's cache boundary.

    `max_dvh`, when not given, is set from the field's own maximum with a
    5% margin, never left at DVH.computeDVH's 100 Gy absolute default:
    evaluator design 7.2, verified 11 September 2026, that default would
    silently truncate accumulated EQD2 in hypofractionated schedules at low
    alpha/beta, exactly the field this function is built to reduce. At 4096
    bins even a wide margin keeps the bin width near 0.05 Gy on a 200 Gy
    axis, so the margin costs nothing in resolution.

    Parameters
    ----------
    eqd2_field : DoseImage-family object
        Accumulated, as returned by bed_to_eqd2.
    roi_mask : ROIMask
    max_dvh : float, Gy, optional
        Explicit override. Passed through unchanged if given: extractor
        design 3.4's rule against defaults applies to the caller's own
        choice here too, this function does not second-guess an explicit
        value against the field's actual maximum.

    Returns
    -------
    DVH, no prescription set: this DVH is on EQD2, where a percentage of
    prescription is not a meaningful quantity (extractor design 7's scope
    note makes the same point for the extractor's own DVH use). Metrics
    read off it, D98/D95/Dmean and gEUD via geud_from_dvh, are all in
    absolute Gy or derived from the histogram directly.
    """
    if max_dvh is None:
        max_dvh = float(eqd2_field.imageArray.max()) * 1.05

    dvh = DVH(roi_mask, eqd2_field)
    dvh.computeDVH(maxDVH=max_dvh)
    return dvh


def geud_from_dvh(dvh, a: float) -> float:
    """gEUD = (sum_i v_i . D_i^a)^(1/a), evaluator design 7.2.

    v_i here must be the *differential* volume fraction in bin i, not the
    cumulative value DVH.histogram returns. Read from the installed
    OpenTPS source on 14 September 2026: `computeDVH` builds `_volume` as
    a cumulative-from-the-top histogram, in percent, "volume receiving at
    least this dose", the standard clinical DVH convention and the same
    one `computeVx`/`computeDx` already rely on. The differential form is
    recovered by a first difference: since `_volume` is non-increasing in
    dose, `volume[i] - volume[i+1]` is exactly the fraction of volume
    whose dose falls in bin i, with the last bin's own cumulative value
    standing in for `volume[i+1] = 0` beyond the axis.

    a = 1/n, evaluator design 7.2: this function takes `a` directly rather
    than `n`, so a caller working from either convention states which one
    it means at the call site instead of this function guessing.

    Uniform dose gives gEUD equal to that dose at any `a`, since a single
    bin then holds essentially all the differential mass; this is the
    identity the tests in evaluator's compose test suite check first.

    Returns
    -------
    float, Gy.
    """
    dose, cum_volume_pct = dvh.histogram
    cum_volume_pct = np.asarray(cum_volume_pct, dtype=np.float64)
    dose = np.asarray(dose, dtype=np.float64)

    diff_volume_pct = -np.diff(cum_volume_pct, append=0.0)
    v = diff_volume_pct / 100.0   # fraction of total ROI volume, sums to ~1

    # dose can be zero or negative in the lowest bin only in pathological
    # cases; guard against 0**a for a < 0, which is the LKB convention
    # (a = 1/n, n small and positive, a large and positive) but not
    # guaranteed by this function's own contract.
    with np.errstate(divide='ignore'):
        powered = np.where(dose > 0, dose ** a, 0.0)

    weighted_sum = np.sum(v * powered)
    return float(weighted_sum ** (1.0 / a))
