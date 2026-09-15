"""Tests for extractor.ingest.

CT and dose are tested against genuine synthetic DICOM files, built with
pydicom directly rather than mocked, so the parsing itself is exercised,
not only this module's own wrapper logic. Struct and plan are tested at
the wrapper-logic level only, via monkeypatch: constructing a minimal but
genuinely valid RTSTRUCT or RTPLAN file, with its nested ROI and beam
sequences, is materially more involved than CT or dose, and is deferred
as a stated scope decision rather than attempted at lower quality. The
None-check logic these two wrappers add is identical in shape to CT and
dose's, already exercised for real there.
"""

import os
import tempfile

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from tps5d.extractor import ingest


# ---------------------------------------------------------------------------
# Synthetic DICOM builders
# ---------------------------------------------------------------------------

def _ct_slice(z, rows=8, cols=8, series_uid=None, frame_uid=None,
             bits_allocated=16, bits_stored=16, high_bit=15):
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.2'
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = Dataset()
    ds.file_meta = file_meta
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = 'CT'
    ds.SeriesInstanceUID = series_uid or generate_uid()
    ds.FrameOfReferenceUID = frame_uid or generate_uid()
    ds.StudyInstanceUID = generate_uid()
    ds.PatientID = 'TEST'
    ds.PatientName = 'Test^Patient'
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = bits_allocated
    ds.BitsStored = bits_stored
    ds.HighBit = high_bit
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.RescaleSlope = 1.0
    ds.RescaleIntercept = -1024.0
    ds.PixelSpacing = [2.0, 2.0]
    ds.ImagePositionPatient = [0.0, 0.0, float(z)]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    dtype = np.uint16 if bits_allocated == 16 else np.uint32
    ds.PixelData = np.full((rows, cols), 1024, dtype=dtype).tobytes()
    return ds


def _write(ds, tmp_path, name):
    p = str(tmp_path / name)
    ds.save_as(p, enforce_file_format=True)
    return p


def _ct_series_paths(tmp_path, n_slices=2, spacing_z=2.0):
    series_uid, frame_uid = generate_uid(), generate_uid()
    paths = []
    for i in range(n_slices):
        ds = _ct_slice(i * spacing_z, series_uid=series_uid, frame_uid=frame_uid)
        paths.append(_write(ds, tmp_path, f'ct_{i}.dcm'))
    return paths, frame_uid


def _dose_dataset(rows=8, cols=8, plan_sop_uid=None, bits_stored=16, bits_allocated=16):
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
    ds.StudyInstanceUID = generate_uid()
    ds.FrameOfReferenceUID = generate_uid()
    ds.PatientID = 'TEST'
    ds.PatientName = 'Test^Patient'
    ds.Rows = rows
    ds.Columns = cols
    ds.NumberOfFrames = 1
    ds.BitsAllocated = bits_allocated
    ds.BitsStored = bits_stored
    ds.HighBit = bits_stored - 1
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.DoseGridScaling = 0.01
    ds.DoseUnits = 'GY'
    ds.DoseType = 'PHYSICAL'
    ds.DoseSummationType = 'PLAN'
    ds.PixelSpacing = [2.0, 2.0]
    ds.SliceThickness = 2.0
    ds.ImagePositionPatient = [0.0, 0.0, 0.0]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    dtype = np.uint16 if bits_stored == 16 else np.uint32
    ds.PixelData = np.full((rows, cols), 200, dtype=dtype).tobytes()

    if plan_sop_uid is not None:
        ref_plan = Dataset()
        ref_plan.ReferencedSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.8'
        ref_plan.ReferencedSOPInstanceUID = plan_sop_uid
        ds.ReferencedRTPlanSequence = [ref_plan]

    return ds


# ---------------------------------------------------------------------------
# ingest_ct
# ---------------------------------------------------------------------------

class TestIngestCT:

    def test_reads_a_real_two_slice_series(self, tmp_path):
        paths, frame_uid = _ct_series_paths(tmp_path, n_slices=2, spacing_z=2.0)

        image = ingest.ingest_ct(paths)

        assert tuple(image.gridSize) == (8, 8, 2)
        assert tuple(np.round(image.spacing, 6)) == (2.0, 2.0, 2.0)
        assert np.allclose(image.imageArray, 0.0)   # 1024*1 - 1024 = 0 HU
        assert image.frameOfReferenceUID == frame_uid

    def test_slice_order_does_not_depend_on_list_order(self, tmp_path):
        paths, _ = _ct_series_paths(tmp_path, n_slices=3, spacing_z=2.0)
        reversed_paths = list(reversed(paths))

        image = ingest.ingest_ct(reversed_paths)

        assert tuple(image.gridSize) == (8, 8, 3)
        assert tuple(np.round(image.spacing, 6)) == (2.0, 2.0, 2.0)

    def test_rejects_empty_list(self):
        with pytest.raises(ValueError, match='no files'):
            ingest.ingest_ct([])

    def test_rejects_single_file(self, tmp_path):
        paths, _ = _ct_series_paths(tmp_path, n_slices=1)
        with pytest.raises(ValueError, match='at least 2'):
            ingest.ingest_ct(paths)


# ---------------------------------------------------------------------------
# ingest_dose
# ---------------------------------------------------------------------------

class TestIngestDose:

    def test_reads_a_real_dose_file_with_plan_reference(self, tmp_path):
        plan_uid = generate_uid()
        ds = _dose_dataset(plan_sop_uid=plan_uid)
        path = _write(ds, tmp_path, 'dose.dcm')

        image = ingest.ingest_dose(path)

        assert tuple(image.gridSize) == (8, 8, 1)
        assert np.allclose(image.imageArray, 2.0)   # 200 * 0.01 Gy
        assert image.referencePlan == plan_uid

    def test_unsupported_bit_depth_raises_instead_of_returning_none(self, tmp_path):
        """readDicomDose returns None for BitsAllocated=8, confirmed
        against the installed source and reproduced directly on
        15 September 2026: only 16- and 32-bit signed/unsigned are
        recognised.
        """
        ds = _dose_dataset(bits_stored=8, bits_allocated=8)
        path = _write(ds, tmp_path, 'bad_dose.dcm')

        with pytest.raises(ValueError, match='Unsupported pixel data type'):
            ingest.ingest_dose(path)


# ---------------------------------------------------------------------------
# ingest_struct, ingest_plan: wrapper-logic tests via monkeypatch
# ---------------------------------------------------------------------------

class TestIngestStructWrapperLogic:

    def test_passes_through_a_successful_parse(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(ingest, 'readDicomStruct', lambda path: sentinel)
        assert ingest.ingest_struct('irrelevant.dcm') is sentinel

    def test_raises_on_none_rather_than_returning_it(self, monkeypatch):
        monkeypatch.setattr(ingest, 'readDicomStruct', lambda path: None)
        with pytest.raises(ValueError, match='SeriesInstanceUID'):
            ingest.ingest_struct('missing_series_uid.dcm')


class TestIngestPlanWrapperLogic:

    def test_passes_through_a_successful_parse(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(ingest, 'readDicomPlan', lambda path: sentinel)
        assert ingest.ingest_plan('irrelevant.dcm') is sentinel

    def test_raises_on_none_rather_than_returning_it(self, monkeypatch):
        monkeypatch.setattr(ingest, 'readDicomPlan', lambda path: None)
        with pytest.raises(ValueError, match='radiation type'):
            ingest.ingest_plan('unsupported_radiation_type.dcm')
