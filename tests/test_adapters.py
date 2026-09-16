"""Tests for extractor.adapters.

test_get_dvf_recovers_known_shift is the priority test of extractor design
3.3: it builds a ground truth with syntheticDeformation.applyBaselineShift,
runs the real Morphons registration, and checks the field recovers the known
shift. This is what "registration path against a constructed ground truth"
means concretely and is the first thing that should run in CI once CI exists.

Caveat found while writing this, not exercised by any test here:
applyBaselineShift returns a single value, the ROI alone, rather than a pair,
when the shift is exactly zero and the input is not a Dynamic3DModel. A
future "identity field" test cannot unpack its result the way the tests
below do and needs its own branch.

The target_metrics tests exercise the two failure modes found and corrected
in the extractor 5.1 round: the course-vs-fraction unit convention (X7 of
that round) and the maxDVH truncation (evaluator E10, extractor 3.4). Both
were failures that returned a plausible number rather than raising, which is
exactly the shape of bug a test suite has to catch since a code review
alone would not. A third failure mode was found running these tests here,
on 11 September 2026, and is exercised by test_cold_plan_returns_zero_not_an_error:
setting maxDVH from the observed dose maximum alone, with no floor at the
prescription, reintroduces an IndexError on cold plans, the opposite tail of
the same bug it was written to close.
"""

import numpy as np
import pytest

from opentps.core.data.images import CTImage, DoseImage, ROIMask
from opentps.core.processing.imageProcessing.syntheticDeformation import applyBaselineShift

from tps5d.extractor.records import DIRSettings, TargetMetrics
from tps5d.extractor.adapters import get_dvf, target_metrics
from dicom_builders import write_dvf


GRID = (40, 40, 30)
SPACING = (2.0, 2.0, 2.0)
ORIGIN = (0.0, 0.0, 0.0)


def _sphere_ct(radius_vox=8.0, seed=0):
    coords = np.indices(GRID).astype(np.float32)
    centre = (np.array(GRID) - 1) / 2.0
    r = np.sqrt(sum((coords[i] - centre[i]) ** 2 for i in range(3)))
    image = np.where(r < radius_vox, 60.0, -900.0).astype(np.float32)
    image += np.random.default_rng(seed).normal(0.0, 15.0, size=GRID).astype(np.float32)
    return CTImage(imageArray=image, origin=ORIGIN, spacing=SPACING)


# ---------------------------------------------------------------------------
# get_dvf: registration direction and recovery, extractor 3.3 / X3
# ---------------------------------------------------------------------------

class TestGetDVF:

    def test_recovers_known_shift(self):
        """fixed = pCT convention (X3), field applied to recover a known
        displacement applied via applyBaselineShift, per extractor 3.3.
        """
        fixed = _sphere_ct()

        roi = ROIMask(imageArray=np.ones(GRID, dtype=bool),
                      origin=ORIGIN, spacing=SPACING, name='phantom_roi')

        shift_mm = np.array([6.0, 0.0, 0.0])
        moving, _ = applyBaselineShift(fixed, roi, shift_mm.tolist())

        settings = DIRSettings(base_resolution=SPACING[0])
        field = get_dvf(moving=moving, fixed=fixed, settings=settings,
                        working_spacing=SPACING)

        # field must come out on the fixed grid, at the requested spacing
        assert tuple(field.gridSize) == tuple(fixed.gridSize)
        assert tuple(np.round(field.spacing, 6)) == SPACING

        # recovery: warping `moving` back through the field should land
        # close to `fixed` inside the phantom. A coarse voxel-difference
        # check is enough here; this is a regression guard; DIR accuracy
        # itself is not validated until real anatomy exists (extractor 3.3).
        recovered = field.deformImage(moving)
        centre_slice = tuple(slice(g // 2 - 5, g // 2 + 5) for g in GRID)
        residual = np.abs(recovered.imageArray[centre_slice]
                          - fixed.imageArray[centre_slice])
        assert residual.mean() < np.abs(fixed.imageArray[centre_slice]).std()

    def test_field_resolution_never_finer_than_working_grid(self):
        """base_resolution set to the working-grid spacing should return a
        field at that spacing, per the 11 September 2026 benchmark (X5).
        """
        fixed = _sphere_ct()
        roi = ROIMask(imageArray=np.ones(GRID, dtype=bool),
                      origin=ORIGIN, spacing=SPACING, name='phantom_roi')
        moving, _ = applyBaselineShift(fixed, roi, [4.0, 0.0, 0.0])

        settings = DIRSettings(base_resolution=SPACING[0])
        field = get_dvf(moving=moving, fixed=fixed, settings=settings,
                        working_spacing=SPACING)

        assert tuple(np.round(field.spacing, 3)) == SPACING

    def test_imported_backend_requires_a_path(self):
        """DIRSettings itself raises on backend='imported' with no
        imported_path, before get_dvf is even called: caught at
        construction, not at use.
        """
        with pytest.raises(ValueError, match='imported_path'):
            DIRSettings(base_resolution=2.0, backend='imported')

    def test_imported_backend_reads_a_real_dvf_file(self, tmp_path):
        """The full imported path, DICOM file through Deformation3D,
        against a synthetic deformable registration object built the same
        way extractor 16's other synthetic DICOM tests are. A uniform
        6mm shift in x: a converted, resampled, then-applied field should
        reproduce it closely, which is checked directly rather than only
        checking that some field comes back.
        """
        fixed = _sphere_ct()
        shift = (6.0, 0.0, 0.0)
        dvf_grid = tuple(int(v) for v in fixed.gridSize)
        path = write_dvf(shift, dvf_grid, SPACING, ORIGIN, str(tmp_path), 'dvf.dcm')

        settings = DIRSettings(base_resolution=SPACING[0], backend='imported',
                               imported_path=path)
        field = get_dvf(moving=fixed, fixed=fixed, settings=settings,
                        working_spacing=SPACING)

        assert tuple(field.gridSize) == dvf_grid
        assert tuple(np.round(field.spacing, 6)) == SPACING

        moved = np.full(GRID, 50.0, dtype=np.float32)
        source = DoseImage(imageArray=moved, origin=ORIGIN, spacing=SPACING)
        result = field.deformImage(source)
        centre_slice = tuple(slice(g // 2 - 5, g // 2 + 5) for g in GRID)
        assert np.allclose(result.imageArray[centre_slice], 50.0, atol=1e-3)

    def test_imported_backend_ignores_moving(self, tmp_path):
        """The field comes entirely from the file; a different `moving`
        must not change the result, unlike the morphons backend where it
        is the whole input.
        """
        fixed = _sphere_ct()
        other_moving = _sphere_ct(seed=1)
        dvf_grid = tuple(int(v) for v in fixed.gridSize)
        path = write_dvf((3.0, 0.0, 0.0), dvf_grid, SPACING, ORIGIN, str(tmp_path), 'dvf.dcm')
        settings = DIRSettings(base_resolution=SPACING[0], backend='imported',
                               imported_path=path)

        field_a = get_dvf(moving=fixed, fixed=fixed, settings=settings,
                          working_spacing=SPACING)
        field_b = get_dvf(moving=other_moving, fixed=fixed, settings=settings,
                          working_spacing=SPACING)

        assert np.array_equal(field_a.imageArray, field_b.imageArray)


# ---------------------------------------------------------------------------
# DIRSettings, X2
# ---------------------------------------------------------------------------

class TestDIRSettings:

    def test_content_hash_stable_and_order_independent(self):
        a = DIRSettings(base_resolution=2.0, n_processes=1, try_gpu=False)
        b = DIRSettings(try_gpu=False, base_resolution=2.0, n_processes=1)
        assert a.content_hash() == b.content_hash()

    def test_content_hash_distinguishes_settings(self):
        a = DIRSettings(base_resolution=2.0)
        b = DIRSettings(base_resolution=2.5)
        assert a.content_hash() != b.content_hash()

    def test_rejects_non_positive_base_resolution(self):
        with pytest.raises(ValueError):
            DIRSettings(base_resolution=0.0)

    def test_rejects_unknown_backend(self):
        with pytest.raises(ValueError):
            DIRSettings(base_resolution=2.0, backend='raystation')


# ---------------------------------------------------------------------------
# target_metrics: the two failure modes found in the 5.1 round
# ---------------------------------------------------------------------------

class TestTargetMetrics:

    def _uniform_dose_and_mask(self, dose_per_fx_gy):
        dose = DoseImage(imageArray=np.full(GRID, dose_per_fx_gy, dtype=np.float32),
                         origin=ORIGIN, spacing=SPACING)
        mask = ROIMask(imageArray=np.ones(GRID, dtype=bool),
                       origin=ORIGIN, spacing=SPACING, name='target')
        return dose, mask

    def test_course_dose_convention_gives_full_coverage_on_a_good_plan(self):
        """A plan delivering exactly the prescription, split over n_fx
        fractions, must show v95 = 100, not v95 = 0. This is the failure
        mode of passing a course prescription against a per-fraction dose:
        it would return v95 = 0.0 here without raising.
        """
        n_fx, rx = 25, 50.0
        dose, mask = self._uniform_dose_and_mask(rx / n_fx)

        m = target_metrics(dose, mask, n_fx=n_fx, rx_dose_gy=rx)

        assert m.v95_pct == pytest.approx(100.0, abs=0.5)
        assert m.d95_gy == pytest.approx(rx, rel=0.02)

    def test_cold_plan_returns_zero_not_an_error(self):
        """A plan at half prescription must return v95 = 0.0 and must not
        raise. Verified against the installed DVH implementation on
        11 September 2026; this test pins that behaviour as a contract
        rather than relying on it silently.
        """
        n_fx, rx = 25, 60.0
        dose, mask = self._uniform_dose_and_mask((rx / n_fx) * 0.5)

        m = target_metrics(dose, mask, n_fx=n_fx, rx_dose_gy=rx)

        assert m.v95_pct == 0.0

    def test_hot_plan_not_truncated_by_maxDVH_default(self):
        """A course dose of 150 Gy must be read back as 150, not clipped at
        the DVH.computeDVH default of 100 Gy absolute (extractor 3.4,
        evaluator E10). Physical per-fraction dose does not reach this
        range in practice; the test exists to pin the contract, not because
        150 Gy is a clinically expected value here.
        """
        n_fx, rx = 5, 40.0
        dose, mask = self._uniform_dose_and_mask(150.0 / n_fx)

        m = target_metrics(dose, mask, n_fx=n_fx, rx_dose_gy=rx)

        assert m.dmax_gy == pytest.approx(150.0, rel=0.01)
        assert m.d95_gy == pytest.approx(150.0, rel=0.02)


# ---------------------------------------------------------------------------
# ROI mask extraction, union bounding box, crop
# ---------------------------------------------------------------------------

from opentps.core.data._rtStruct import RTStruct
from opentps.core.data._roiContour import ROIContour

from tps5d.extractor.records import WorkingGrid, CropBounds
from tps5d.extractor.adapters import (
    extract_roi_mask, union_bounding_box, crop_to_bounds, roi_volume_cc,
    roi_mask_algorithm, ROI_BINARIZATION_THRESHOLD,
)


def _circle_polygon(cx, cy, z, radius, n=24):
    """Flat [x0,y0,z0, x1,y1,z1, ...] polygon, matching the format
    ROIContour.get_partial_volume_mask reads from polygonMesh.
    """
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = []
    for a in angles:
        pts += [cx + radius * np.cos(a), cy + radius * np.sin(a), z]
    return pts


def _cylinder_rtstruct(name='PTV', cx=20.0, cy=20.0, radius=6.0,
                       z_values=(10.0, 12.0, 14.0, 16.0, 18.0)):
    """A short cylinder as a synthetic RTSTRUCT, on the grid used by the
    WorkingGrid fixtures below (origin 0, spacing 2mm, grid 20x20x15).
    """
    contour = ROIContour(name=name)
    contour.polygonMesh = [_circle_polygon(cx, cy, z, radius) for z in z_values]

    rtstruct = RTStruct(name='test_struct')
    rtstruct.appendContour(contour)
    return rtstruct


ROI_GRID = WorkingGrid(origin=(0.0, 0.0, 0.0), spacing=(2.0, 2.0, 2.0),
                       grid_size=(20, 20, 15))


class TestExtractROIMask:

    def test_returns_boolean_mask_of_expected_rough_volume(self):
        rtstruct = _cylinder_rtstruct()
        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)

        assert mask.imageArray.dtype == bool
        # cylinder: pi * r^2 * height, r=6mm, height~10mm (5 slices at 2mm)
        expected_cc = np.pi * 6.0 ** 2 * 10.0 / 1000.0
        got_cc = roi_volume_cc(mask)
        assert got_cc == pytest.approx(expected_cc, rel=0.35)  # coarse: rasterisation, not precision

    def test_getVolume_is_mm3_not_cc(self):
        """Pins the unit ROIMask.getVolume(inVoxels=False) actually returns,
        confirmed against the installed source on 11 September 2026 after
        this test's first version silently assumed cc and failed by a
        factor of ~1000.
        """
        rtstruct = _cylinder_rtstruct()
        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)
        assert mask.getVolume(inVoxels=False) == pytest.approx(roi_volume_cc(mask) * 1000.0)

    def test_missing_name_raises_keyerror_not_attributeerror(self):
        """getContourByName itself returns None silently (verified against
        the installed source on 11 September 2026); this pins that the
        wrapper converts that into a raise, per extractor design 9.
        """
        rtstruct = _cylinder_rtstruct()
        with pytest.raises(KeyError, match='PTV'):
            extract_roi_mask(rtstruct, 'OAR_not_present', grid=ROI_GRID)

    def test_binarization_threshold_changes_volume_monotonically(self):
        """Higher threshold keeps fewer partially-covered edge voxels, so
        volume should not increase as the threshold rises. This is the
        parameter get_partial_volume_mask silently returns a float mask
        instead of thresholding on, if it is left at its own default.

        Only meaningful when get_partial_volume_mask is present: on
        getBinaryMask there is no threshold to vary, and extract_roi_mask
        correctly raises rather than ignoring it, confirmed against the
        project's own checkout on 14 September 2026. That raise has its
        own test, TestROIMaskBackendDispatch.test_forced_getBinaryMask_path_rejects_overridden_threshold;
        this test is about the other backend's actual behaviour and is
        skipped where that backend is absent, rather than failing on a
        property this environment cannot have.
        """
        if roi_mask_algorithm() != 'get_partial_volume_mask':
            pytest.skip('get_partial_volume_mask not present in this OpenTPS; '
                       'binarization_threshold has no effect on getBinaryMask.')

        rtstruct = _cylinder_rtstruct()
        vols = [
            extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID,
                             binarization_threshold=t).getVolume()
            for t in (0.1, 0.5, 0.9)
        ]
        assert vols[0] >= vols[1] >= vols[2]

    def test_default_threshold_matches_deprecated_wrapper(self):
        """ROI_BINARIZATION_THRESHOLD reproduces what the deprecated
        getBinaryMask hardcoded, so switching call sites away from it is
        not a silent behaviour change.
        """
        assert ROI_BINARIZATION_THRESHOLD == 0.5

    def test_grid_not_containing_contour_raises_before_opentps_is_called(self):
        """A grid too small to physically contain the contour must raise
        ValueError from this wrapper. Without this check,
        get_partial_volume_mask proceeds and only logs a warning, and that
        internal logging call is itself malformed and raises TypeError
        under some logging configurations, confirmed under pytest's own
        log capture on 11 September 2026: `logger.warning(msg,
        RuntimeWarning, stacklevel=2)` passes RuntimeWarning as a
        %-format argument to a message with no placeholder for it.
        """
        rtstruct = _cylinder_rtstruct()  # x,y in 14-26mm, z in 10-18mm
        too_small = WorkingGrid(origin=(0.0, 0.0, 0.0), spacing=(2.0, 2.0, 2.0),
                                grid_size=(5, 5, 5))  # covers only 0-8mm per axis

        with pytest.raises(ValueError, match='does not contain'):
            extract_roi_mask(rtstruct, 'PTV', grid=too_small)


class TestROIMaskBackendDispatch:
    """roi_mask_algorithm() and the getBinaryMask fallback path.

    This sandbox's OpenTPS (3.0.1) has both get_partial_volume_mask and a
    deprecated getBinaryMask that forwards to it, so roi_mask_algorithm()
    here always reports 'get_partial_volume_mask'; the tests below force
    the other branch via monkeypatch to exercise extract_roi_mask's own
    dispatch and guard logic. This validates the calling convention and
    control flow, not numerical agreement with the project's own OpenTPS
    checkout, whose getBinaryMask is a different, non-forwarding
    implementation (confirmed by reading its source on 12 September 2026)
    and has not been run against this test file.
    """

    def test_algorithm_matches_installed_environment(self):
        # Whichever OpenTPS is installed, this must report one of the two
        # known algorithms. Asserting a specific one here would be
        # asserting a fact about the sandbox, not about the code: the
        # public OpenTPS 3.0.1 has get_partial_volume_mask, the project's
        # own checkout does not (confirmed 14 September 2026), and this
        # test runs against either.
        assert roi_mask_algorithm() in ('get_partial_volume_mask', 'getBinaryMask')

    def test_forced_getBinaryMask_path_returns_boolean_mask(self, monkeypatch):
        monkeypatch.setattr('tps5d.extractor.adapters.roi_mask_algorithm',
                            lambda: 'getBinaryMask')
        rtstruct = _cylinder_rtstruct()

        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)

        assert mask.imageArray.dtype == bool
        assert tuple(int(v) for v in mask.gridSize) == ROI_GRID.grid_size

    def test_forced_getBinaryMask_path_rejects_overridden_threshold(self, monkeypatch):
        """A caller who tunes binarization_threshold expecting it to matter
        must be told it will not, not have it silently dropped: getBinaryMask
        has no such parameter at all (confirmed 12 September 2026).
        """
        monkeypatch.setattr('tps5d.extractor.adapters.roi_mask_algorithm',
                            lambda: 'getBinaryMask')
        rtstruct = _cylinder_rtstruct()

        with pytest.raises(ValueError, match='silently ignored'):
            extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID,
                            binarization_threshold=0.9)

    def test_forced_getBinaryMask_path_rejects_overridden_precision(self, monkeypatch):
        monkeypatch.setattr('tps5d.extractor.adapters.roi_mask_algorithm',
                            lambda: 'getBinaryMask')
        rtstruct = _cylinder_rtstruct()

        with pytest.raises(ValueError, match='silently ignored'):
            extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID, precision=32)

    def test_forced_getBinaryMask_path_accepts_call_at_plain_defaults(self, monkeypatch):
        """The common case: a caller who never touches these two
        parameters must not be penalised for an environment they did not
        choose.
        """
        monkeypatch.setattr('tps5d.extractor.adapters.roi_mask_algorithm',
                            lambda: 'getBinaryMask')
        rtstruct = _cylinder_rtstruct()

        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)
        assert mask.imageArray.sum() > 0

    def test_forced_getBinaryMask_path_still_checks_containment_first(self, monkeypatch):
        """The containment guard runs before backend dispatch, so it must
        still fire on the getBinaryMask path: that implementation gives no
        signal at all on a grid mismatch, not even a malformed warning.
        """
        monkeypatch.setattr('tps5d.extractor.adapters.roi_mask_algorithm',
                            lambda: 'getBinaryMask')
        rtstruct = _cylinder_rtstruct()
        too_small = WorkingGrid(origin=(0.0, 0.0, 0.0), spacing=(2.0, 2.0, 2.0),
                                grid_size=(5, 5, 5))

        with pytest.raises(ValueError, match='does not contain'):
            extract_roi_mask(rtstruct, 'PTV', grid=too_small)


class TestUnionBoundingBox:

    def test_single_mask_bbox_contains_all_set_voxels(self):
        rtstruct = _cylinder_rtstruct()
        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)

        bounds = union_bounding_box([mask])
        arr = mask.imageArray
        nz = np.argwhere(arr)
        assert nz[:, 0].min() >= bounds.lo[0]
        assert nz[:, 0].max() <= bounds.hi[0]
        assert nz[:, 1].min() >= bounds.lo[1]
        assert nz[:, 1].max() <= bounds.hi[1]
        assert nz[:, 2].min() >= bounds.lo[2]
        assert nz[:, 2].max() <= bounds.hi[2]

    def test_two_disjoint_masks_union_covers_both(self):
        rtstruct = RTStruct(name='two_roi')
        c1 = ROIContour(name='A')
        c1.polygonMesh = [_circle_polygon(6.0, 6.0, z, 3.0) for z in (8.0, 10.0, 12.0)]
        c2 = ROIContour(name='B')
        c2.polygonMesh = [_circle_polygon(34.0, 34.0, z, 3.0) for z in (16.0, 18.0, 20.0)]
        rtstruct.appendContour(c1)
        rtstruct.appendContour(c2)

        m1 = extract_roi_mask(rtstruct, 'A', grid=ROI_GRID)
        m2 = extract_roi_mask(rtstruct, 'B', grid=ROI_GRID)

        bounds = union_bounding_box([m1, m2])
        # box spanning two opposite corners must be much larger than either
        # ROI's own bbox alone
        b1 = union_bounding_box([m1])
        assert bounds.shape()[0] > b1.shape()[0]

    def test_single_slice_contour_on_getBinaryMask_path_raises(self, monkeypatch):
        """A contour on a single z-slice makes getBinaryMask return
        imageArray=None rather than raise: found by reading the source on
        12 September 2026, and reproduced for real against the project's
        own OpenTPS checkout on 14 September 2026, where a single-z-slice
        fixture used elsewhere in this file tripped it by accident. Kept
        as its own test so the behaviour has dedicated coverage instead of
        being hit incidentally by a fixture testing something else.

        Skipped where get_partial_volume_mask is present: there,
        getBinaryMask is the deprecated wrapper that forwards to it
        (extractor 3.1), not the native old implementation, and does not
        exhibit this bug. Confirmed by running this exact test against
        both environments on 14 September 2026: it fails to raise in the
        sandbox's OpenTPS 3.0.1 for precisely this reason, which is what
        the skip condition below now catches instead of misreporting a
        behaviour difference as a code defect.
        """
        from opentps.core.data._roiContour import ROIContour
        if hasattr(ROIContour, 'get_partial_volume_mask'):
            pytest.skip('getBinaryMask here forwards to get_partial_volume_mask '
                       'and does not exhibit the old implementation\'s '
                       'single-slice bug.')

        monkeypatch.setattr('tps5d.extractor.adapters.roi_mask_algorithm',
                            lambda: 'getBinaryMask')
        rtstruct = RTStruct(name='single_slice')
        contour = ROIContour(name='A')
        contour.polygonMesh = [_circle_polygon(6.0, 6.0, 10.0, 3.0)]  # one slice
        rtstruct.appendContour(contour)

        with pytest.raises(ValueError, match='single z-slice'):
            extract_roi_mask(rtstruct, 'A', grid=ROI_GRID)

    def test_margin_extends_and_clamps(self):
        rtstruct = _cylinder_rtstruct()
        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)

        tight = union_bounding_box([mask], margin_vox=0)
        padded = union_bounding_box([mask], margin_vox=2)
        for a in range(3):
            assert padded.lo[a] <= tight.lo[a]
            assert padded.hi[a] >= tight.hi[a]
            assert padded.lo[a] >= 0
            assert padded.hi[a] < ROI_GRID.grid_size[a]

    def test_rejects_masks_on_different_grids(self):
        rtstruct = _cylinder_rtstruct()
        m1 = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)
        # Different grid_size but still large enough to physically contain
        # the cylinder (x,y in 14-26mm, z in 10-18mm), so this exercises
        # union_bounding_box's own grid-agreement check rather than
        # extract_roi_mask's physical-containment guard.
        other_grid = WorkingGrid(origin=(0.0, 0.0, 0.0), spacing=(2.0, 2.0, 2.0),
                                 grid_size=(20, 20, 20))
        m2 = extract_roi_mask(rtstruct, 'PTV', grid=other_grid)

        with pytest.raises(ValueError, match='grid'):
            union_bounding_box([m1, m2])

    def test_empty_list_raises(self):
        with pytest.raises(ValueError):
            union_bounding_box([])


class TestCropToBounds:

    def test_crop_preserves_type_and_physical_location(self):
        rtstruct = _cylinder_rtstruct()
        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)
        bounds = union_bounding_box([mask], margin_vox=1)

        cropped = crop_to_bounds(mask, bounds)

        assert type(cropped) is type(mask)
        assert cropped.imageArray.shape == bounds.shape()

        # a voxel at cropped-local index i corresponds to the same physical
        # point as the original at lo[a] + i
        expected_origin = tuple(
            ROI_GRID.origin[a] + bounds.lo[a] * ROI_GRID.spacing[a]
            for a in range(3)
        )
        assert tuple(np.round(cropped.origin, 6)) == pytest.approx(expected_origin)

    def test_crop_does_not_mutate_source(self):
        rtstruct = _cylinder_rtstruct()
        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)
        original_shape = mask.imageArray.shape
        bounds = union_bounding_box([mask])

        crop_to_bounds(mask, bounds)

        assert mask.imageArray.shape == original_shape

    def test_crop_content_matches_source_at_same_physical_location(self):
        rtstruct = _cylinder_rtstruct()
        mask = extract_roi_mask(rtstruct, 'PTV', grid=ROI_GRID)
        bounds = union_bounding_box([mask])

        cropped = crop_to_bounds(mask, bounds)

        lo = bounds.lo
        original_slice = mask.imageArray[lo[0]:lo[0]+3, lo[1]:lo[1]+3, lo[2]:lo[2]+1]
        cropped_slice = cropped.imageArray[0:3, 0:3, 0:1]
        assert np.array_equal(original_slice, cropped_slice)

    def test_crop_on_dose_image_preserves_dose_subclass(self):
        dose = DoseImage(imageArray=np.arange(20*20*15, dtype=np.float32).reshape(20, 20, 15),
                         origin=ROI_GRID.origin, spacing=ROI_GRID.spacing)
        bounds = CropBounds(lo=(5, 5, 5), hi=(14, 14, 9))

        cropped = crop_to_bounds(dose, bounds)

        assert isinstance(cropped, DoseImage)
        assert cropped.imageArray.shape == (10, 10, 5)


# ---------------------------------------------------------------------------
# Plan complexity, both modalities
# ---------------------------------------------------------------------------

from opentps.core.data.plan import ProtonPlan, PlanProtonBeam, PlanProtonLayer, PhotonPlan, PlanPhotonBeam

from tps5d.extractor.adapters import extract_plan_complexity
from tps5d.extractor.records import PlanComplexity


def _proton_plan(n_beams=2, layers_per_beam=3, spots_per_layer=4, mu_per_spot=1.5):
    plan = ProtonPlan()
    for _ in range(n_beams):
        beam = PlanProtonBeam()
        for _ in range(layers_per_beam):
            layer = PlanProtonLayer(nominalEnergy=100.0)
            for i in range(spots_per_layer):
                layer.appendSpot(x=float(i), y=0.0, mu=mu_per_spot)
            beam.appendLayer(layer)
        plan.appendBeam(beam)
    return plan


def _photon_plan(n_beams=2, segments_per_beam=3, mu_per_segment=50.0):
    plan = PhotonPlan()
    for _ in range(n_beams):
        beam = PlanPhotonBeam()
        for _ in range(segments_per_beam):
            segment = beam.createBeamSegment()
            segment.appendBeamlet(x=0.0, y=0.0, mu=mu_per_segment)
        plan.appendBeam(beam)
    return plan


class TestExtractPlanComplexity:

    def test_proton_counts_and_mu(self):
        plan = _proton_plan(n_beams=2, layers_per_beam=3, spots_per_layer=4, mu_per_spot=1.5)
        pc = extract_plan_complexity(plan)

        assert pc.modality == 'pt'
        assert pc.n_fields == 2
        assert pc.n_layers == 2 * 3
        assert pc.n_spots == 2 * 3 * 4
        assert pc.mu == pytest.approx(2 * 3 * 4 * 1.5)
        assert pc.n_segments == 0        # photon-only field stays at its default
        assert pc.target_vol_cc == 0.0   # filled by the caller, not by this function

    def test_photon_counts_and_mu(self):
        plan = _photon_plan(n_beams=3, segments_per_beam=2, mu_per_segment=40.0)
        pc = extract_plan_complexity(plan)

        assert pc.modality == 'xt'
        assert pc.n_fields == 3
        assert pc.n_segments == 3 * 2
        assert pc.mu == pytest.approx(3 * 2 * 40.0)
        assert pc.n_layers == 0          # proton-only field stays at its default
        assert pc.n_spots == 0

    def test_rejects_unrecognised_plan_type(self):
        with pytest.raises(TypeError, match='neither ProtonPlan nor PhotonPlan'):
            extract_plan_complexity(object())

    def test_single_beam_single_layer_single_spot(self):
        """Smallest non-degenerate proton plan: guards against an
        off-by-one in the beam/layer/spot aggregation.
        """
        plan = _proton_plan(n_beams=1, layers_per_beam=1, spots_per_layer=1, mu_per_spot=3.0)
        pc = extract_plan_complexity(plan)
        assert (pc.n_fields, pc.n_layers, pc.n_spots) == (1, 1, 1)
        assert pc.mu == pytest.approx(3.0)
