"""Tests for evaluator.compose.

Each function is tested against values this suite computes independently of
the module, and against `ntcp.py` directly, so that agreement with `ntcp.py`
holds by construction and not by coincidence. The evaluator 4.2 worked example
(1 Gy next to 5 Gy, alpha/beta 3, target voxel midway) runs through the whole
chain at the end of the file.
"""

import numpy as np
import pytest

from opentps.core.data.images import DoseImage, ROIMask, Deformation3D, VectorField3D

from tps5d.evaluator import ntcp
from tps5d.evaluator.compose import (
    compute_bed, warp_bed, sum_bed, bed_to_eqd2, reduce_to_dvh, geud_from_dvh,
)


GRID = (10, 10, 8)
SPACING = (2.0, 2.0, 2.0)
ORIGIN = (0.0, 0.0, 0.0)


def _uniform_dose(value, grid=GRID, spacing=SPACING, origin=ORIGIN):
    return DoseImage(imageArray=np.full(grid, value, dtype=np.float32),
                     origin=origin, spacing=spacing)


def _full_mask(grid=GRID, spacing=SPACING, origin=ORIGIN):
    return ROIMask(imageArray=np.ones(grid, dtype=bool),
                   origin=origin, spacing=spacing, name='roi')


class TestComputeBed:

    def test_matches_hand_calculation(self):
        """BED = n.d.(1 + d/(a/b)): d=2.0, n=25, a/b=3.0
        -> 25 * 2.0 * (1 + 2/3) = 50 * 1.6667 = 83.333...
        """
        dose = _uniform_dose(2.0)
        bed = compute_bed(dose, n_b=25, alpha_beta=3.0)
        expected = 25 * 2.0 * (1 + 2.0 / 3.0)
        assert np.allclose(bed.imageArray, expected, rtol=1e-5)

    def test_preserves_geometry_and_type(self):
        dose = _uniform_dose(2.0)
        bed = compute_bed(dose, n_b=25, alpha_beta=3.0)
        assert isinstance(bed, DoseImage)
        assert tuple(bed.gridSize) == GRID
        assert tuple(np.round(bed.spacing, 6)) == SPACING

    def test_does_not_mutate_input(self):
        dose = _uniform_dose(2.0)
        original = dose.imageArray.copy()
        compute_bed(dose, n_b=25, alpha_beta=3.0)
        assert np.array_equal(dose.imageArray, original)

    def test_zero_dose_gives_zero_bed(self):
        dose = _uniform_dose(0.0)
        bed = compute_bed(dose, n_b=25, alpha_beta=3.0)
        assert np.allclose(bed.imageArray, 0.0)

    def test_agrees_with_ntcp_bed_directly(self):
        """Not a coincidence of matching arithmetic: this calls ntcp.bed
        with the equivalent total-dose input and checks the same number
        comes out, confirming compute_bed actually delegates rather than
        having its own parallel formula (evaluator 11.5, the ntcp.py
        reconciliation of 14 September 2026).
        """
        d, n_fx, ab = 3.5, 12, 2.5
        dose = _uniform_dose(d)
        bed = compute_bed(dose, n_b=n_fx, alpha_beta=ab)

        expected = ntcp.bed(dose=d * n_fx, n_fx=n_fx, ab=ab)
        assert np.allclose(bed.imageArray, expected, rtol=1e-6)


class TestBedToEqd2:

    def test_two_gy_per_fraction_reproduces_physical_dose_at_any_alpha_beta(self):
        """Analytic identity, not specific to this codebase: at exactly
        2 Gy/fraction, EQD2 equals total physical dose regardless of
        alpha/beta, since BED = D(1+1) [with d/(a/b) cancelling against
        the +2/(a/b) term in the EQD2 denominator when d=2]. Checked
        algebraically before being used as a test: EQD2 = D(a/b+2)/(a/b+2)
        = D exactly, for any a/b > 0.
        """
        n_fx, d = 25, 2.0
        total_dose = n_fx * d
        dose = _uniform_dose(d)

        for alpha_beta in (1.5, 3.0, 10.0):
            bed = compute_bed(dose, n_b=n_fx, alpha_beta=alpha_beta)
            eqd2 = bed_to_eqd2(bed, alpha_beta=alpha_beta)
            assert np.allclose(eqd2.imageArray, total_dose, rtol=1e-5), alpha_beta

    def test_hypofractionated_numbers_from_evaluator_7_2(self):
        """5 x 8 Gy at alpha/beta 2 -> 100 Gy EQD2; 5 x 10 Gy at alpha/beta 3
        -> 130 Gy EQD2. These are the exact numbers evaluator design 7.2
        cites for why DVH.computeDVH's 100 Gy absolute default would
        silently truncate. Independently recomputed here before being used
        as a fixture: BED = 5*8*(1+8/2) = 200, EQD2 = 200/(1+2/2) = 100.
        BED = 5*10*(1+10/3) = 216.667, EQD2 = 216.667/(1+2/3) = 130.0.
        """
        dose_a = _uniform_dose(8.0)
        bed_a = compute_bed(dose_a, n_b=5, alpha_beta=2.0)
        eqd2_a = bed_to_eqd2(bed_a, alpha_beta=2.0)
        assert np.allclose(eqd2_a.imageArray, 100.0, rtol=1e-4)

        dose_b = _uniform_dose(10.0)
        bed_b = compute_bed(dose_b, n_b=5, alpha_beta=3.0)
        eqd2_b = bed_to_eqd2(bed_b, alpha_beta=3.0)
        assert np.allclose(eqd2_b.imageArray, 130.0, rtol=1e-4)

    def test_agrees_with_ntcp_eqd2_from_bed_directly(self):
        bed_value = 47.3
        bed_field = _uniform_dose(bed_value)
        eqd2_field = bed_to_eqd2(bed_field, alpha_beta=2.7)

        expected = ntcp.eqd2_from_bed(bed_value, ab=2.7)
        assert np.allclose(eqd2_field.imageArray, expected, rtol=1e-6)


class TestSumBed:

    def test_sums_elementwise(self):
        f1 = _uniform_dose(10.0)
        f2 = _uniform_dose(20.0)
        f3 = _uniform_dose(5.0)
        total = sum_bed([f1, f2, f3])
        assert np.allclose(total.imageArray, 35.0)

    def test_single_field_returns_itself_in_value(self):
        f1 = _uniform_dose(42.0)
        total = sum_bed([f1])
        assert np.allclose(total.imageArray, 42.0)

    def test_rejects_empty_list(self):
        with pytest.raises(ValueError, match='no fields'):
            sum_bed([])

    def test_rejects_mismatched_shapes(self):
        f1 = _uniform_dose(1.0, grid=(10, 10, 8))
        f2 = _uniform_dose(1.0, grid=(5, 5, 5))
        with pytest.raises(ValueError, match='grid'):
            sum_bed([f1, f2])

    def test_rejects_mismatched_origin(self):
        f1 = _uniform_dose(1.0, origin=(0.0, 0.0, 0.0))
        f2 = _uniform_dose(1.0, origin=(10.0, 0.0, 0.0))
        with pytest.raises(ValueError, match='grid'):
            sum_bed([f1, f2])

    def test_does_not_mutate_inputs(self):
        f1 = _uniform_dose(10.0)
        f2 = _uniform_dose(20.0)
        sum_bed([f1, f2])
        assert np.allclose(f1.imageArray, 10.0)
        assert np.allclose(f2.imageArray, 20.0)


class TestWarpBed:

    @staticmethod
    def _shift_x(mm):
        """A deformation shifting the sampling point by `mm` along x."""
        arr = np.zeros(GRID + (3,), dtype=np.float32)
        arr[..., 0] = mm
        dvf = Deformation3D()
        dvf.initFromDisplacementField(VectorField3D(imageArray=arr, origin=ORIGIN, spacing=SPACING))
        return dvf

    @staticmethod
    def _ramp():
        ramp = np.broadcast_to(10.0 * np.arange(GRID[0], dtype=np.float32)[:, None, None], GRID).copy()
        return DoseImage(imageArray=ramp, origin=ORIGIN, spacing=SPACING)

    @staticmethod
    def _slab(i0, i1):
        arr = np.zeros(GRID, dtype=bool)
        arr[i0:i1] = True
        return ROIMask(imageArray=arr, origin=ORIGIN, spacing=SPACING, name='slab')

    def test_samples_the_field_and_fills_outside_with_zero(self):
        """A shift of one voxel: output i is the input at i + 1, and the last
        plane, whose source lies outside the grid, is filled with 0."""
        out = warp_bed(self._ramp(), self._shift_x(2.0), rois=[self._slab(1, 6)]).imageArray
        assert np.allclose(out[:GRID[0] - 1], 10.0 * np.arange(1, GRID[0])[:, None, None])
        assert np.all(out[-1] == 0.0)

    def test_raises_when_an_roi_would_be_partly_filled(self):
        """Q3: the ROI must lie inside the warped extent, or the DVH describes a
        different volume. Raise, not warn."""
        with pytest.raises(ValueError, match='map outside'):
            warp_bed(self._ramp(), self._shift_x(2.0), rois=[self._slab(5, GRID[0])])

    def test_raises_when_the_bed_field_is_not_on_the_grid_of_the_deformation(self):
        other = _uniform_dose(1.0, grid=(10, 10, 9))
        with pytest.raises(ValueError, match='not on the same grid'):
            warp_bed(other, self._shift_x(0.0), rois=[])


class TestReduceToDvh:

    def test_max_dvh_from_field_maximum_not_truncated_at_100gy(self):
        """The evaluator 7.2 finding this function exists to prevent:
        an accumulated EQD2 field at 130 Gy must read back as 130, not be
        clipped at DVH.computeDVH's 100 Gy absolute default.
        """
        eqd2 = _uniform_dose(130.0)
        mask = _full_mask()

        dvh = reduce_to_dvh(eqd2, mask)

        assert dvh.Dmax == pytest.approx(130.0, rel=0.01)
        assert dvh.D95 == pytest.approx(130.0, rel=0.02)

    def test_a_mask_off_the_field_grid_or_empty_raises(self):
        """DVH would resample a mismatched mask by interpolation and dilate it."""
        eqd2 = _uniform_dose(60.0)
        shifted = _full_mask(origin=(1.0, 0.0, 0.0))
        empty = ROIMask(imageArray=np.zeros(GRID, dtype=bool), origin=ORIGIN,
                        spacing=SPACING, name='roi')
        with pytest.raises(ValueError, match='same grid'):
            reduce_to_dvh(eqd2, shifted)
        with pytest.raises(ValueError, match='empty'):
            reduce_to_dvh(eqd2, empty)

    def test_explicit_max_dvh_is_honoured_unchanged(self):
        eqd2 = _uniform_dose(50.0)
        mask = _full_mask()

        dvh = reduce_to_dvh(eqd2, mask, max_dvh=200.0)

        assert dvh.Dmax == pytest.approx(50.0, rel=0.01)


class TestGeudFromDvh:

    def test_uniform_dose_gives_geud_equal_to_dose_at_any_n(self):
        eqd2 = _uniform_dose(60.0)
        mask = _full_mask()
        dvh = reduce_to_dvh(eqd2, mask)

        for n in (1.0, 0.09, 0.2, 3.0):
            geud = geud_from_dvh(dvh, n)
            assert geud == pytest.approx(60.0, rel=1e-3), n

    def test_two_value_case_matches_hand_calculation(self):
        """Half the ROI at 40 Gy, half at 80 Gy, n = 0.5 (a = 1/n = 2).
        gEUD = (0.5*40^2 + 0.5*80^2)^(1/2) = (800 + 3200)^0.5 = 4000^0.5
             = 63.2455... Gy, computed independently of the module under
        test before being used as the expected value.
        """
        array = np.empty(GRID, dtype=np.float32)
        half = GRID[2] // 2
        array[:, :, :half] = 40.0
        array[:, :, half:] = 80.0
        eqd2 = DoseImage(imageArray=array, origin=ORIGIN, spacing=SPACING)
        mask = _full_mask()

        dvh = reduce_to_dvh(eqd2, mask)
        geud = geud_from_dvh(dvh, n=0.5)

        expected = (0.5 * 40.0 ** 2 + 0.5 * 80.0 ** 2) ** 0.5
        assert geud == pytest.approx(expected, rel=1e-3)

    def test_small_volume_parameter_approaches_max_dose(self):
        """As n -> small (a serial-like organ), gEUD should approach the
        maximum dose present, the power-mean limit. Not an exact equality
        test, a direction-and-bound check: gEUD must lie between the mean
        and the max, and move toward the max as n shrinks.
        """
        array = np.empty(GRID, dtype=np.float32)
        half = GRID[2] // 2
        array[:, :, :half] = 40.0
        array[:, :, half:] = 80.0
        eqd2 = DoseImage(imageArray=array, origin=ORIGIN, spacing=SPACING)
        mask = _full_mask()
        dvh = reduce_to_dvh(eqd2, mask)

        geud_large_n = geud_from_dvh(dvh, n=1.0)     # equals the mean, 60.0
        geud_small_n = geud_from_dvh(dvh, n=0.05)    # should approach 80.0

        assert geud_large_n == pytest.approx(60.0, rel=1e-3)
        assert geud_small_n > geud_large_n
        assert geud_small_n < 80.0
        assert geud_small_n > 75.0   # should be close to the max by n=0.05

    def test_agrees_with_ntcp_geud_from_cumulative_dvh_directly(self):
        eqd2 = _uniform_dose(55.0)
        mask = _full_mask()
        dvh = reduce_to_dvh(eqd2, mask)

        got = geud_from_dvh(dvh, n=0.09)
        dose_bins, cum_volume_pct = dvh.histogram
        expected = ntcp.geud_from_cumulative_dvh(dose_bins, cum_volume_pct, n=0.09)

        assert got == pytest.approx(expected, rel=1e-9)



# Evaluator 4.2 worked example, through the pipeline

def test_evaluator_4_2_worked_example_through_the_pipeline():
    """Evaluator 4.2: alpha/beta 3, one fraction, 1 Gy next to 5 Gy, target voxel
    midway (uniform shift of one voxel half-width). Convert, deform, sum,
    convert once gives 4.40 Gy; deform first and convert afterwards gives 3.60
    Gy. Zero displacement cannot distinguish these, nor the sign of the shift
    (the other neighbour would give 0.80 Gy)."""
    grid, sp, org = (10, 10, 8), (2.0, 2.0, 2.0), (0.0, 0.0, 0.0)
    a = np.full(grid, 5.0, dtype = np.float32)
    a[:5] = 1.0                          # axis-0 planes 0..4 at 1 Gy, 5..9 at 5 Gy
    dose = DoseImage(imageArray = a, origin = org, spacing = sp)

    disp = np.zeros(grid + (3,), dtype = np.float32)
    disp[..., 0] = 1.0
    dvf = Deformation3D()
    dvf.initFromDisplacementField(VectorField3D(imageArray = disp, origin = org, spacing = sp))
    ab = 3.0
    inside = np.zeros(grid, dtype = bool)
    inside[:9] = True                    # the last plane would sample outside the grid
    everywhere = ROIMask(imageArray = inside, origin = org, spacing = sp, name = 'roi')

    good = bed_to_eqd2(sum_bed([warp_bed(compute_bed(dose, 1, ab), dvf, rois = [everywhere])]), ab)
    bad = bed_to_eqd2(compute_bed(warp_bed(dose, dvf, rois = [everywhere]), 1, ab), ab)

    assert good.imageArray[4, 5, 4] == pytest.approx(4.40, abs = 1e-3)
    assert bad.imageArray[4, 5, 4] == pytest.approx(3.60, abs = 1e-3)
    assert good.imageArray[1, 5, 4] == pytest.approx(0.80, abs = 1e-3)
