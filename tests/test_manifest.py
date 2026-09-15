"""Tests for extractor.manifest."""

import os
import re

import numpy as np
import pytest
from pydicom.uid import generate_uid

from opentps.core.data.images import DoseImage
from opentps.core.data.plan import ProtonPlan
from opentps.core.data._rtStruct import RTStruct

from tps5d.extractor.manifest import (
    read_manifest, check_row_consistency, check_manifest, ManifestRow,
    discover_and_load, _find_dicom_by_sop_uid,
)
from dicom_builders import write_dose, write_proton_plan, write_struct


HEADER = "plan_uid,path,block_index,arm,role,source_image_uid,n_fx,dose_per_fx_gy"


def _write(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text("\n".join([HEADER] + lines) + "\n", encoding='utf-8')
    return str(path)


def _aligned_triple(uid='plan-1', frame='frame-1'):
    """A dose/plan/struct triple that agrees with itself, for tests that
    perturb one field at a time away from consistency.
    """
    dose = DoseImage(imageArray=np.zeros((2, 2, 2), dtype=np.float32),
                     origin=(0, 0, 0), spacing=(1, 1, 1))
    dose.referencePlan = uid

    plan = ProtonPlan()
    plan.sopInstanceUID = uid
    plan.frameOfReferenceUID = frame

    struct = RTStruct(name='s')
    struct.frameOfReferenceUID = frame

    return dose, plan, struct


class TestReadManifest:

    def test_parses_rows_and_reconstructs_fx_scheme(self, tmp_path):
        path = _write(tmp_path, "m.csv", [
            "plan-1,doses/plan-1.dcm,0,PT-A,planned,frame-1,25,2.0",
        ])
        rows = read_manifest(path)

        assert len(rows) == 1
        r = rows[0]
        assert r.plan_uid == 'plan-1'
        assert r.block_index == 0
        assert r.arm == 'PT-A'
        assert r.role == 'planned'
        assert r.fx_scheme == (25, 2.0)

    def test_rejects_invalid_arm(self, tmp_path):
        path = _write(tmp_path, "m.csv", [
            "plan-1,doses/plan-1.dcm,0,PT-Z,planned,frame-1,25,2.0",
        ])
        with pytest.raises(ValueError, match='arm'):
            read_manifest(path)

    def test_rejects_invalid_role(self, tmp_path):
        path = _write(tmp_path, "m.csv", [
            "plan-1,doses/plan-1.dcm,0,PT-A,provisional,frame-1,25,2.0",
        ])
        with pytest.raises(ValueError, match='role'):
            read_manifest(path)

    def test_rejects_non_integer_block_index(self, tmp_path):
        path = _write(tmp_path, "m.csv", [
            "plan-1,doses/plan-1.dcm,one,PT-A,planned,frame-1,25,2.0",
        ])
        with pytest.raises(ValueError, match='block_index'):
            read_manifest(path)

    def test_rejects_wrong_header(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text("plan_uid,path\nplan-1,x\n", encoding='utf-8')
        with pytest.raises(ValueError, match='header'):
            read_manifest(str(path))

    def test_rejects_empty_manifest(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text(HEADER + "\n", encoding='utf-8')
        with pytest.raises(ValueError, match='no rows'):
            read_manifest(str(path))

    def test_rescue_rows_are_ordinary_extra_rows(self, tmp_path):
        """The row count is not fixed in advance (extractor design 4):
        two rows for the same block, one planned and one rescue, must both
        read cleanly.
        """
        path = _write(tmp_path, "m.csv", [
            "plan-1,doses/plan-1.dcm,0,PT-NA,planned,frame-1,25,2.0",
            "plan-1-rescue,doses/plan-1-rescue.dcm,0,PT-NA,rescue,frame-2,25,2.0",
        ])
        rows = read_manifest(path)
        assert len(rows) == 2
        assert rows[1].role == 'rescue'


class TestCheckRowConsistency:

    def _row(self, plan_uid='plan-1', block_index=0):
        return ManifestRow(plan_uid=plan_uid, path='x.dcm', block_index=block_index,
                           arm='PT-A', role='planned', source_image_uid='frame-1',
                           fx_scheme=(25, 2.0))

    def test_passes_when_aligned(self):
        dose, plan, struct = _aligned_triple()
        check_row_consistency(self._row(), dose=dose, plan=plan, struct=struct)  # no raise

    def test_catches_dose_plan_mismatch(self):
        dose, plan, struct = _aligned_triple()
        dose.referencePlan = 'someone-elses-plan'
        with pytest.raises(ValueError, match='referencePlan'):
            check_row_consistency(self._row(), dose=dose, plan=plan, struct=struct)

    def test_catches_manifest_plan_uid_mismatch(self):
        dose, plan, struct = _aligned_triple(uid='plan-1')
        with pytest.raises(ValueError, match='plan_uid'):
            check_row_consistency(self._row(plan_uid='plan-2'), dose=dose, plan=plan, struct=struct)

    def test_catches_frame_of_reference_mismatch(self):
        dose, plan, struct = _aligned_triple()
        struct.frameOfReferenceUID = 'a-different-frame'
        with pytest.raises(ValueError, match='frameOfReferenceUID'):
            check_row_consistency(self._row(), dose=dose, plan=plan, struct=struct)

    def test_reports_multiple_problems_at_once(self):
        dose, plan, struct = _aligned_triple()
        dose.referencePlan = 'wrong'
        struct.frameOfReferenceUID = 'wrong-frame'
        with pytest.raises(ValueError) as excinfo:
            check_row_consistency(self._row(), dose=dose, plan=plan, struct=struct)
        msg = str(excinfo.value)
        assert 'referencePlan' in msg
        assert 'frameOfReferenceUID' in msg


class TestCheckManifest:

    def test_collects_problems_across_rows(self):
        dose1, plan1, struct1 = _aligned_triple(uid='plan-1', frame='frame-1')
        dose2, plan2, struct2 = _aligned_triple(uid='plan-2', frame='frame-2')
        dose2.referencePlan = 'not-plan-2'   # break the second row only

        rows = [
            ManifestRow('plan-1', 'x', 0, 'PT-A', 'planned', 'frame-1', (25, 2.0)),
            ManifestRow('plan-2', 'y', 1, 'PT-A', 'planned', 'frame-2', (25, 2.0)),
        ]
        loaded = {'plan-1': (dose1, plan1, struct1), 'plan-2': (dose2, plan2, struct2)}

        with pytest.raises(ValueError, match='plan-2'):
            check_manifest(rows, loaded)

    def test_passes_when_every_row_is_consistent(self):
        dose1, plan1, struct1 = _aligned_triple(uid='plan-1', frame='frame-1')
        rows = [ManifestRow('plan-1', 'x', 0, 'PT-A', 'planned', 'frame-1', (25, 2.0))]
        loaded = {'plan-1': (dose1, plan1, struct1)}
        check_manifest(rows, loaded)  # no raise

    def test_reports_missing_loaded_triple(self):
        rows = [ManifestRow('plan-1', 'x', 0, 'PT-A', 'planned', 'frame-1', (25, 2.0))]
        with pytest.raises(ValueError, match='no loaded dose/plan/struct'):
            check_manifest(rows, {})


class TestDiscoverAndLoad:

    def _write_triple(self, tmp_path, n_fx_value=25.0):
        """dose -> plan -> struct, all in the same directory, wired
        together through the same reference chain check_row_consistency
        checks.
        """
        struct_path, struct_uid, frame_uid = write_struct(
            {'Rectum_dicom_name': (39.0, 39.0, [23.0, 25.0, 27.0], 6.0)},
            str(tmp_path), 'struct.dcm',
        )
        plan_path, plan_uid = write_proton_plan(
            str(tmp_path), 'plan.dcm', n_spots=2,
            referenced_struct_sop_uid=struct_uid, frame_of_reference_uid=frame_uid,
        )
        dose_path = write_dose(2.0, (10, 10, 8), (2.0, 2.0, 2.0), (0.0, 0.0, 0.0),
                               str(tmp_path), 'dose.dcm', plan_sop_uid=plan_uid)
        return dose_path, plan_uid, struct_uid

    def test_discovers_and_loads_the_real_triple(self, tmp_path):
        dose_path, plan_uid, struct_uid = self._write_triple(tmp_path)
        row = ManifestRow(plan_uid=str(plan_uid), path=dose_path, block_index=0,
                          arm='PT-A', role='planned', source_image_uid='frame-1',
                          fx_scheme=(25, 2.0))

        dose, plan, struct = discover_and_load(row)

        assert dose.referencePlan == plan_uid
        assert plan.sopInstanceUID == plan_uid
        assert struct.sopInstanceUID == struct_uid

    def test_discovered_triple_passes_consistency_check(self, tmp_path):
        """The point of discovery: what it returns must satisfy
        check_row_consistency without modification.
        """
        dose_path, plan_uid, struct_uid = self._write_triple(tmp_path)
        row = ManifestRow(plan_uid=str(plan_uid), path=dose_path, block_index=0,
                          arm='PT-A', role='planned', source_image_uid='frame-1',
                          fx_scheme=(25, 2.0))

        dose, plan, struct = discover_and_load(row)
        check_row_consistency(row, dose=dose, plan=plan, struct=struct)  # no raise

    def test_explicit_search_dir_overrides_dose_path_directory(self, tmp_path):
        """A layout where the three files are not siblings of row.path."""
        other_dir = tmp_path / 'elsewhere'
        other_dir.mkdir()
        struct_path, struct_uid, frame_uid = write_struct(
            {'Rectum_dicom_name': (39.0, 39.0, [23.0, 25.0], 6.0)},
            str(other_dir), 'struct.dcm',
        )
        plan_path, plan_uid = write_proton_plan(
            str(other_dir), 'plan.dcm', referenced_struct_sop_uid=struct_uid,
            frame_of_reference_uid=frame_uid,
        )
        dose_dir = tmp_path / 'dose_only'
        dose_dir.mkdir()
        dose_path = write_dose(2.0, (10, 10, 8), (2.0, 2.0, 2.0), (0.0, 0.0, 0.0),
                               str(dose_dir), 'dose.dcm', plan_sop_uid=plan_uid)

        row = ManifestRow(plan_uid=str(plan_uid), path=dose_path, block_index=0,
                          arm='PT-A', role='planned', source_image_uid='frame-1',
                          fx_scheme=(25, 2.0))

        with pytest.raises(FileNotFoundError):
            discover_and_load(row)  # default search_dir is dose_dir, which has no plan

        dose, plan, struct = discover_and_load(row, search_dir=str(other_dir))
        assert plan.sopInstanceUID == plan_uid

    def test_raises_clearly_when_plan_not_found(self, tmp_path):
        """A syntactically valid but unreferenced UID, not a human-readable
        placeholder: pydicom validates the VR of a UI-type field on write,
        and a string like 'no-such-plan' is not a valid UID, which pydicom
        correctly warns about. The point under test is "not found", not
        "malformed", so the fixture should not conflate the two.
        """
        missing_plan_uid = generate_uid()
        dose_path = write_dose(2.0, (10, 10, 8), (2.0, 2.0, 2.0), (0.0, 0.0, 0.0),
                               str(tmp_path), 'dose.dcm', plan_sop_uid=missing_plan_uid)
        row = ManifestRow(plan_uid=missing_plan_uid, path=dose_path, block_index=0,
                          arm='PT-A', role='planned', source_image_uid='frame-1',
                          fx_scheme=(25, 2.0))

        with pytest.raises(FileNotFoundError, match=re.escape(missing_plan_uid)):
            discover_and_load(row)

    def test_raises_clearly_when_struct_not_found(self, tmp_path):
        missing_struct_uid = generate_uid()
        plan_path, plan_uid = write_proton_plan(
            str(tmp_path), 'plan.dcm', referenced_struct_sop_uid=missing_struct_uid,
        )
        dose_path = write_dose(2.0, (10, 10, 8), (2.0, 2.0, 2.0), (0.0, 0.0, 0.0),
                               str(tmp_path), 'dose.dcm', plan_sop_uid=plan_uid)
        row = ManifestRow(plan_uid=str(plan_uid), path=dose_path, block_index=0,
                          arm='PT-A', role='planned', source_image_uid='frame-1',
                          fx_scheme=(25, 2.0))

        with pytest.raises(FileNotFoundError, match=re.escape(missing_struct_uid)):
            discover_and_load(row)

    def test_raises_on_duplicate_sop_instance_uid_in_directory(self, tmp_path):
        """A byte-copy of the plan file has the same SOPInstanceUID, since
        that UID lives in the file's own content: the simplest real way
        to construct a genuine duplicate rather than simulate one.
        """
        import shutil

        dose_path, plan_uid, struct_uid = self._write_triple(tmp_path)
        original_plan_path = str(tmp_path / 'plan.dcm')
        shutil.copy(original_plan_path, str(tmp_path / 'plan_copy.dcm'))

        row = ManifestRow(plan_uid=str(plan_uid), path=dose_path, block_index=0,
                          arm='PT-A', role='planned', source_image_uid='frame-1',
                          fx_scheme=(25, 2.0))

        with pytest.raises(ValueError, match='claim SOPInstanceUID'):
            discover_and_load(row)


class TestFindDicomBySopUid:

    def test_finds_the_matching_file_among_several(self, tmp_path):
        _, uid_a, _ = write_struct({'A': (10.0, 10.0, [5.0, 7.0], 3.0)}, str(tmp_path), 'a.dcm')
        _, uid_b, _ = write_struct({'B': (20.0, 20.0, [5.0, 7.0], 3.0)}, str(tmp_path), 'b.dcm')

        found = _find_dicom_by_sop_uid(str(tmp_path), uid_b)
        assert found.endswith('b.dcm')

    def test_raises_file_not_found_on_no_match(self, tmp_path):
        write_struct({'A': (10.0, 10.0, [5.0, 7.0], 3.0)}, str(tmp_path), 'a.dcm')
        with pytest.raises(FileNotFoundError):
            _find_dicom_by_sop_uid(str(tmp_path), 'not-present')

    def test_skips_non_dicom_files_silently(self, tmp_path):
        (tmp_path / 'readme.txt').write_text('not a dicom file', encoding='utf-8')
        _, uid_a, _ = write_struct({'A': (10.0, 10.0, [5.0, 7.0], 3.0)}, str(tmp_path), 'a.dcm')

        found = _find_dicom_by_sop_uid(str(tmp_path), uid_a)
        assert found.endswith('a.dcm')
