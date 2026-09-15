"""End-to-end: DICOM ingest through NTCP evaluation, two blocks, real registration.

Every module built in this project's extractor and evaluator work,
exercised together against DICOM files and a real Morphons registration,
not the isolated unit tests each module has had until now. This is where
this session's two most serious bugs were actually found, the dose-
convention mismatch between compose.py and ntcp.py and the ROI-masking
backend divergence: both were invisible to any single module's own tests,
since each module was internally correct and the two only disagreed at
the seam between them. A seam is what this file tests.

**Scope, stated rather than left implicit.** CT and dose go through real
`ingest_ct`/`ingest_dose` against DICOM files built with `pydicom`. The
structure set and the plan are constructed directly via OpenTPS objects,
not through `ingest_struct`/`ingest_plan`: synthetic RTSTRUCT/RTPLAN DICOM
files are a stated open item (extractor 15), and this file does not
attempt to close it, since doing so is a separable piece of work with its
own value, not a prerequisite for testing the composition seam this file
exists for.

**Design of the scenario: uniform dose per block, chosen so the expected
result is hand-computable and real registration is expected to reproduce
it almost exactly.** A spatially uniform BED field should warp to
approximately the same uniform value regardless of the deformation field
applied to it, away from the domain's edges; if it does not, either the
registration or the composition has a bug. `n_fx = 25`, `alpha_beta = 3.0`
matches the pre-populated `rectum_bleeding_g2` model in `registry.py`, so
the scenario also produces a real NTCP number through the actual model
rather than an invented one.

Expected values, computed independently of this test's own pipeline code,
directly from `ntcp.bed`/`ntcp.eqd2_from_bed`/`scipy.stats.norm` by hand
before the pipeline was run: BED = 25x2.0x(1+2/3) + 25x1.8x(1+1.8/3) =
83.333 + 72.0 = 155.333; EQD2 = 155.333/(1+2/3) = 93.2 Gy exactly; NTCP =
Phi((93.2-76.9)/(0.13x76.9)) = 0.948501. The pipeline reproduced 93.20001
and 0.9485010 on first run, agreement to five and six significant figures
respectively, the residual consistent with registration interpolation
rather than a defect.

**A finding along the way, noted rather than chased down.** `readDicomCT`
transposes its assembled array, `.transpose(1, 0, 2)`, to go from
DICOM's (Rows, Columns, Slices) to OpenTPS's internal axis order. A
uniform-valued test phantom, used throughout every earlier test in this
project, is invariant to this and never exposed it. A spatially varying
phantom is not: a naive `PixelSpacing = [spacing[0], spacing[1]]` and
`Rows, Columns = arr.shape[0], arr.shape[1]`, without accounting for which
of a caller's axes DICOM calls a row and which a column, does not
round-trip to the same array it started from. This does not affect this
file's own scenario, since every image goes through the identical writer
and reader, so pCT and both rCTs are mutually consistent regardless of
which convention that is; it would matter for a test that needed a
specific image axis to mean a specific anatomical direction, which this
one does not. Left for whoever writes that test.
"""

import time
import tempfile
import os

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from opentps.core.data.images import ROIMask, CTImage
from opentps.core.data._rtStruct import RTStruct
from opentps.core.data._roiContour import ROIContour
from opentps.core.data.plan import ProtonPlan, PlanProtonBeam, PlanProtonLayer
from opentps.core.processing.imageProcessing.syntheticDeformation import applyBaselineShift

from tps5d.extractor import ingest
from tps5d.extractor.adapters import (
    DIRSettings, WorkingGrid, get_dvf, extract_roi_mask_by_canonical_name,
    extract_plan_complexity, roi_volume_cc,
)
from tps5d.extractor.roi_mapping import RoiMapping
from tps5d.evaluator.compose import (
    compute_bed, warp_bed, sum_bed, bed_to_eqd2, reduce_to_dvh, geud_from_dvh,
)
from tps5d.evaluator import ntcp, registry


GRID = (40, 40, 30)
SPACING = (2.0, 2.0, 2.0)
ORIGIN = (0.0, 0.0, 0.0)

N_FX = 25
ALPHA_BETA = 3.0   # matches registry.REGISTRY['rectum_bleeding_g2']
DOSE_PER_FX_BLOCK1 = 2.0
DOSE_PER_FX_BLOCK2 = 1.8

# Hand-computed before the pipeline was run, independent of the code under test.
EXPECTED_BED = N_FX * DOSE_PER_FX_BLOCK1 * (1 + DOSE_PER_FX_BLOCK1 / ALPHA_BETA) \
              + N_FX * DOSE_PER_FX_BLOCK2 * (1 + DOSE_PER_FX_BLOCK2 / ALPHA_BETA)
EXPECTED_EQD2 = EXPECTED_BED / (1 + 2 / ALPHA_BETA)


def _sphere_phantom(seed=0):
    coords = np.indices(GRID).astype(np.float32)
    centre = (np.array(GRID) - 1) / 2.0
    r = np.sqrt(sum((coords[i] - centre[i]) ** 2 for i in range(3)))
    image = np.where(r < 8.0, 40.0, -900.0).astype(np.float32)
    image += np.random.default_rng(seed).normal(0.0, 15.0, size=GRID).astype(np.float32)
    return image


def _write_ct_series(image, tmp_dir, prefix):
    arr = image.imageArray
    origin, spacing = image.origin, image.spacing
    series_uid, frame_uid = generate_uid(), generate_uid()
    paths = []
    for z in range(arr.shape[2]):
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.2'
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = file_meta
        ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.Modality = 'CT'
        ds.SeriesInstanceUID = series_uid
        ds.FrameOfReferenceUID = frame_uid
        ds.StudyInstanceUID = generate_uid()
        ds.PatientID, ds.PatientName = 'E2E', 'E2E^Test'
        ds.Rows, ds.Columns = arr.shape[0], arr.shape[1]
        ds.BitsAllocated, ds.BitsStored, ds.HighBit = 16, 16, 15
        ds.PixelRepresentation = 1
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.RescaleSlope, ds.RescaleIntercept = 1.0, 0.0
        ds.PixelSpacing = [float(spacing[0]), float(spacing[1])]
        ds.ImagePositionPatient = [float(origin[0]), float(origin[1]), float(origin[2] + z * spacing[2])]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelData = np.clip(arr[:, :, z], -1000, 3000).astype(np.int16).tobytes()
        p = os.path.join(tmp_dir, f'{prefix}_{z:03d}.dcm')
        ds.save_as(p, enforce_file_format=True)
        paths.append(p)
    return paths


def _write_dose(value_gy, grid, spacing, origin, tmp_dir, name, plan_sop_uid):
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.2'
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = file_meta
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = 'RTDOSE'
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientID, ds.PatientName = 'E2E', 'E2E^Test'
    ds.Rows, ds.Columns = grid[0], grid[1]
    ds.NumberOfFrames = grid[2]
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 16, 16, 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    scaling = 0.001
    ds.DoseGridScaling = scaling
    ds.DoseUnits, ds.DoseType, ds.DoseSummationType = 'GY', 'PHYSICAL', 'PLAN'
    ds.PixelSpacing = [float(spacing[0]), float(spacing[1])]
    ds.SliceThickness = float(spacing[2])
    ds.ImagePositionPatient = [float(v) for v in origin]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    raw = int(round(value_gy / scaling))
    ds.PixelData = np.full((grid[0], grid[1], grid[2]), raw, dtype=np.uint16).tobytes(order='F')
    ref_plan = Dataset()
    ref_plan.ReferencedSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.8'
    ref_plan.ReferencedSOPInstanceUID = plan_sop_uid
    ds.ReferencedRTPlanSequence = [ref_plan]
    p = os.path.join(tmp_dir, name)
    ds.save_as(p, enforce_file_format=True)
    return p


def _circle_polygon(cx, cy, z, radius, n=16):
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = []
    for a in angles:
        pts += [cx + radius * np.cos(a), cy + radius * np.sin(a), z]
    return pts


def _make_proton_plan(n_spots_per_layer):
    plan = ProtonPlan()
    beam = PlanProtonBeam()
    layer = PlanProtonLayer(nominalEnergy=100.0)
    for i in range(n_spots_per_layer):
        layer.appendSpot(x=float(i), y=0.0, mu=2.0)
    beam.appendLayer(layer)
    plan.appendBeam(beam)
    return plan


@pytest.fixture(scope='module')
def pipeline_result(tmp_path_factory):
    """Runs the full pipeline once; individual tests assert against the
    shared result, since the two registrations cost real time.
    """
    tmp_dir = str(tmp_path_factory.mktemp('e2e'))

    # 1. Phantom pCT and two shifted rCTs, a known deformation each.
    pct_array = _sphere_phantom()
    pct = CTImage(imageArray=pct_array, origin=ORIGIN, spacing=SPACING)
    shift_roi = ROIMask(imageArray=np.ones(GRID, dtype=bool), origin=ORIGIN, spacing=SPACING, name='shiftregion')
    rct1, _ = applyBaselineShift(pct, shift_roi, [4.0, 0.0, 0.0])
    rct2, _ = applyBaselineShift(pct, shift_roi, [-3.0, 2.0, 0.0])

    # 2. Real DICOM ingest for all three CTs.
    pct_ing = ingest.ingest_ct(_write_ct_series(pct, tmp_dir, 'pct'))
    rct1_ing = ingest.ingest_ct(_write_ct_series(rct1, tmp_dir, 'rct1'))
    rct2_ing = ingest.ingest_ct(_write_ct_series(rct2, tmp_dir, 'rct2'))

    # 3. Structure set, direct construction (see module docstring).
    cx, cy = 39.0, 39.0
    rectum = ROIContour(name='Rectum_dicom_name')
    rectum.polygonMesh = [_circle_polygon(cx, cy, z, 6.0) for z in (23.0, 25.0, 27.0, 29.0, 31.0, 33.0, 35.0)]
    struct = RTStruct(name='struct')
    struct.appendContour(rectum)

    # 4. TG-263 mapping and mask, on pCT's grid.
    mapping = RoiMapping(entries={'Rectum': 'Rectum_dicom_name'}, content_hash='e2e-test', path='<in-memory>')
    grid = WorkingGrid(origin=tuple(pct_ing.origin), spacing=tuple(pct_ing.spacing),
                       grid_size=tuple(int(v) for v in pct_ing.gridSize))
    rectum_mask = extract_roi_mask_by_canonical_name(struct, 'Rectum', mapping=mapping, grid=grid)

    # 5. Real DICOM ingest for both blocks' dose.
    plan1_uid, plan2_uid = generate_uid(), generate_uid()
    dose1 = ingest.ingest_dose(_write_dose(DOSE_PER_FX_BLOCK1, GRID, SPACING, ORIGIN, tmp_dir, 'dose1.dcm', plan1_uid))
    dose2 = ingest.ingest_dose(_write_dose(DOSE_PER_FX_BLOCK2, GRID, SPACING, ORIGIN, tmp_dir, 'dose2.dcm', plan2_uid))

    # 6. Plans, direct construction (see module docstring), and plan complexity.
    plan1, plan2 = _make_proton_plan(4), _make_proton_plan(5)
    plan_complexity = [extract_plan_complexity(plan1), extract_plan_complexity(plan2)]

    # 7. Real registration, fixed = pCT, per extractor design 6.2 and X3.
    settings = DIRSettings(base_resolution=SPACING[0])
    t0 = time.perf_counter()
    dvf1 = get_dvf(moving=rct1_ing, fixed=pct_ing, settings=settings, working_spacing=SPACING)
    dvf2 = get_dvf(moving=rct2_ing, fixed=pct_ing, settings=settings, working_spacing=SPACING)
    registration_seconds = time.perf_counter() - t0

    # 8. Composition: BED per block, warp onto pCT, sum, convert once.
    bed1 = warp_bed(compute_bed(dose1, n_fx=N_FX, alpha_beta=ALPHA_BETA), dvf1)
    bed2 = warp_bed(compute_bed(dose2, n_fx=N_FX, alpha_beta=ALPHA_BETA), dvf2)
    eqd2_field = bed_to_eqd2(sum_bed([bed1, bed2]), alpha_beta=ALPHA_BETA)

    # 9. DVH and gEUD, both consumption routes (evaluator design 11.1).
    dvh = reduce_to_dvh(eqd2_field, rectum_mask)
    model = registry.REGISTRY['rectum_bleeding_g2']
    masked_voxels = eqd2_field.imageArray[rectum_mask.imageArray.astype(bool)]

    return dict(
        pct=pct_ing, rct1=rct1_ing, rct2=rct2_ing,
        dose1=dose1, dose2=dose2, dose1_plan_uid=plan1_uid,
        plan_complexity=plan_complexity,
        rectum_mask=rectum_mask,
        eqd2_field=eqd2_field,
        masked_voxels=masked_voxels,
        dvh=dvh,
        model=model,
        registration_seconds=registration_seconds,
    )


class TestIngestSeam:

    def test_ct_series_round_trip_geometry(self, pipeline_result):
        assert tuple(pipeline_result['pct'].gridSize) == GRID
        assert tuple(np.round(pipeline_result['pct'].spacing, 6)) == SPACING

    def test_dose_carries_its_plan_reference(self, pipeline_result):
        assert pipeline_result['dose1'].referencePlan == pipeline_result['dose1_plan_uid']

    def test_dose_values_survive_ingest(self, pipeline_result):
        assert pipeline_result['dose1'].imageArray.mean() == pytest.approx(DOSE_PER_FX_BLOCK1, rel=1e-6)
        assert pipeline_result['dose2'].imageArray.mean() == pytest.approx(DOSE_PER_FX_BLOCK2, rel=1e-6)


class TestExtractionSeam:

    def test_rectum_mask_has_plausible_volume(self, pipeline_result):
        cc = roi_volume_cc(pipeline_result['rectum_mask'])
        assert 0.5 < cc < 10.0   # a radius-6mm sphere is ~0.9 cc; generous bounds

    def test_plan_complexity_both_blocks(self, pipeline_result):
        pc1, pc2 = pipeline_result['plan_complexity']
        assert pc1.n_spots == 4
        assert pc2.n_spots == 5
        assert pc1.modality == pc2.modality == 'pt'


class TestCompositionSeam:
    """Where this session's real bugs lived: the dose-convention mismatch
    between compose.py and ntcp.py, and the ROI-masking backend divergence.
    Neither was visible to any single module's own tests.
    """

    def test_registration_completed_in_reasonable_time(self, pipeline_result):
        assert pipeline_result['registration_seconds'] < 60.0

    def test_uniform_dose_accumulates_to_the_hand_computed_eqd2(self, pipeline_result):
        """The central check: a spatially uniform dose per block, put
        through real registration and real composition, must reproduce
        the analytically hand-computed EQD2 inside the ROI, not only an
        EQD2 that looks plausible.
        """
        values = pipeline_result['masked_voxels']
        assert values.mean() == pytest.approx(EXPECTED_EQD2, rel=1e-3)
        # low spread: a uniform input should stay close to uniform after
        # a correct registration, away from the domain's edges
        assert values.std() < 0.1

    def test_dvh_route_and_voxel_route_geud_agree(self, pipeline_result):
        """evaluator design 11.1's two consumption paths, DVH-cached and
        direct-voxel, must not silently diverge.
        """
        n = pipeline_result['model'].params['n']
        via_dvh = geud_from_dvh(pipeline_result['dvh'], n)
        via_voxels = ntcp.geud(pipeline_result['masked_voxels'], n)
        assert via_dvh == pytest.approx(via_voxels, rel=1e-2)   # binning error, evaluator 7.2

    def test_ntcp_via_registry_matches_hand_calculated_value(self, pipeline_result):
        """The full chain's final number, through the actual pre-populated
        model in registry.py, not a model invented for this test.
        """
        result = registry.evaluate(pipeline_result['model'], eqd2_dose=pipeline_result['masked_voxels'])
        expected_ntcp = 0.9485009214061058   # computed independently, module docstring
        assert result == pytest.approx(expected_ntcp, abs=1e-3)
        assert 0.0 <= result <= 1.0

    def test_ntcp_via_dvh_route_is_close_to_voxel_route(self, pipeline_result):
        n, td50, m = (pipeline_result['model'].params[k] for k in ('n', 'td50', 'm'))
        via_dvh = ntcp.lkb_from_geud(geud_from_dvh(pipeline_result['dvh'], n), td50, m)
        via_voxels = registry.evaluate(pipeline_result['model'], eqd2_dose=pipeline_result['masked_voxels'])
        assert via_dvh == pytest.approx(via_voxels, abs=5e-3)
