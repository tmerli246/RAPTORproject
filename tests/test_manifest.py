"""Tests for extractor.manifest."""

import numpy as np
import pytest

from opentps.core.data.images import DoseImage
from opentps.core.data.plan import ProtonPlan
from opentps.core.data._rtStruct import RTStruct

from tps5d.extractor.manifest import (
    read_manifest, check_row_consistency, check_manifest, ManifestRow,
)


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
