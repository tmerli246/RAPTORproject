"""Synthetic DICOM builders shared across test files.

Not a test file: pytest does not collect this, since it has no test_
functions of its own. Factored out because CT, dose, struct and plan
construction is now needed in more than one test file, extractor 16's
open item on synthetic struct/plan files among them, and duplicating it
per file would mean three places to fix the same DICOM tag if one of them
were wrong.

Every function here writes the minimum set of tags that got a file
through the corresponding `readDicomXxx` on the first attempt, confirmed
against the installed source on 15 September 2026, not the full tag set a
real export would carry.
"""

import os

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid


def write_ct_series(image, tmp_dir: str, prefix: str) -> list:
    """One DICOM file per z-slice of an Image3D-family object's array.

    Axis note: `Rows, Columns = arr.shape[0], arr.shape[1]` here, without
    correcting for DICOM's own Rows/Columns convention. `readDicomCT`
    applies its own `.transpose(1, 0, 2)` on read, so a round trip through
    this writer and that reader is internally consistent, but the result
    is not guaranteed to preserve which of the caller's axes is which
    physical direction. Every test using this function only needs
    internal consistency, not a specific anatomical axis meaning; see
    evaluator design 11.6.
    """
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
        ds.PatientID, ds.PatientName = 'TEST', 'Test^Patient'
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


def write_dose(value_gy: float, grid, spacing, origin, tmp_dir: str, name: str,
               plan_sop_uid: str = None) -> str:
    """One RTDOSE file, uniform value, referencing `plan_sop_uid` if given."""
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
    ds.PatientID, ds.PatientName = 'TEST', 'Test^Patient'
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
    if plan_sop_uid is not None:
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


def write_struct(rois: dict, tmp_dir: str, name: str, frame_of_reference_uid: str = None):
    """One RTSTRUCT file with one contour per entry in `rois`.

    rois : dict of {dicom_name: (cx, cy, z_values, radius)}, one sphere-like
           contour per entry, built from `_circle_polygon` at each z.

    Returns
    -------
    (path, sop_instance_uid, frame_of_reference_uid)
    """
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.3'
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = file_meta
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = 'RTSTRUCT'
    ds.SeriesInstanceUID = generate_uid()
    ds.FrameOfReferenceUID = frame_of_reference_uid or generate_uid()
    ds.PatientID, ds.PatientName = 'TEST', 'Test^Patient'

    roi_seq, contour_seq = [], []
    for i, (dicom_name, (cx, cy, z_values, radius)) in enumerate(rois.items(), start=1):
        roi = Dataset()
        roi.ROINumber = i
        roi.ROIName = dicom_name
        roi.ReferencedFrameOfReferenceUID = ds.FrameOfReferenceUID
        roi_seq.append(roi)

        contours = []
        for z in z_values:
            c = Dataset()
            c.ContourData = _circle_polygon(cx, cy, z, radius)
            contours.append(c)

        roi_contour = Dataset()
        roi_contour.ReferencedROINumber = i
        roi_contour.ROIDisplayColor = [255, 0, 0]
        roi_contour.ContourSequence = contours
        contour_seq.append(roi_contour)

    ds.StructureSetROISequence = roi_seq
    ds.ROIContourSequence = contour_seq

    p = os.path.join(tmp_dir, name)
    ds.save_as(p, enforce_file_format=True)
    return p, ds.SOPInstanceUID, ds.FrameOfReferenceUID


def write_proton_plan(tmp_dir: str, name: str, *, n_spots: int = 2,
                      referenced_struct_sop_uid: str = None,
                      frame_of_reference_uid: str = None):
    """One minimal RT Ion Plan file, one beam, one layer, `n_spots` spots.

    Returns
    -------
    (path, sop_instance_uid)
    """
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.8'
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = file_meta
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = 'RTPLAN'
    ds.SeriesInstanceUID = generate_uid()
    ds.FrameOfReferenceUID = frame_of_reference_uid or generate_uid()
    ds.PatientID, ds.PatientName = 'TEST', 'Test^Patient'

    fg = Dataset()
    fg.NumberOfFractionsPlanned = 25
    fg.NumberOfBeams = 1
    fg.FractionGroupNumber = 1
    rb = Dataset()
    rb.ReferencedBeamNumber = 1
    rb.BeamMeterset = 100.0
    fg.ReferencedBeamSequence = [rb]
    ds.FractionGroupSequence = [fg]

    cp = Dataset()
    cp.IsocenterPosition = [0.0, 0.0, 0.0]
    cp.GantryAngle = 0.0
    cp.PatientSupportAngle = 0.0
    cp.NumberOfScanSpotPositions = n_spots
    cp.ScanSpotMetersetWeights = [100.0 / n_spots] * n_spots
    cp.NominalBeamEnergy = 120.0
    position_map = []
    for i in range(n_spots):
        position_map += [float(i) * 5.0, 0.0]
    cp.ScanSpotPositionMap = position_map

    beam = Dataset()
    beam.RadiationType = 'PROTON'
    beam.ScanMode = 'MODULATED'
    beam.TreatmentDeliveryType = 'TREATMENT'
    beam.BeamName = 'B1'
    beam.BeamNumber = 1
    beam.FinalCumulativeMetersetWeight = 100.0
    beam.NumberOfRangeShifters = 0
    beam.IonControlPointSequence = [cp]
    ds.IonBeamSequence = [beam]

    if referenced_struct_sop_uid is not None:
        ref_struct = Dataset()
        ref_struct.ReferencedSOPClassUID = '1.2.840.10008.5.1.4.1.1.481.3'
        ref_struct.ReferencedSOPInstanceUID = referenced_struct_sop_uid
        ds.ReferencedStructureSetSequence = [ref_struct]

    p = os.path.join(tmp_dir, name)
    ds.save_as(p, enforce_file_format=True)
    return p, ds.SOPInstanceUID


def write_dvf(displacement_xyz, grid, spacing, origin, tmp_dir: str, name: str):
    """One minimal DICOM deformable registration object.

    displacement_xyz : (3,) sequence, mm, a uniform displacement applied
        everywhere on the grid. Uniform rather than spatially varying,
        matching this project's own preference for hand-checkable fields
        (evaluator design 11.6): a converted, resampled field carrying a
        known uniform displacement is trivial to verify against by eye.
    grid : (nx, ny, nz)

    Returns
    -------
    path : str
    """
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.66.3'
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = Dataset()
    ds.file_meta = file_meta
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = 'REG'
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientID, ds.PatientName = 'TEST', 'Test^Patient'

    nx, ny, nz = grid
    field = np.zeros((3, nx, ny, nz), dtype=np.float32)
    for axis in range(3):
        field[axis, ...] = float(displacement_xyz[axis])

    grid_ds = Dataset()
    grid_ds.ImagePositionPatient = [float(v) for v in origin]
    grid_ds.GridResolution = [float(v) for v in spacing]
    grid_ds.GridDimensions = [nx, ny, nz]
    grid_ds.VectorGridData = field.tobytes(order='F')

    reg_seq_ds = Dataset()
    reg_seq_ds.DeformableRegistrationGridSequence = [grid_ds]
    ds.DeformableRegistrationSequence = [reg_seq_ds]

    p = os.path.join(tmp_dir, name)
    ds.save_as(p, enforce_file_format=True)
    return p
