"""Tests for extractor.roi_mapping."""

import numpy as np
import pytest

from opentps.core.data._rtStruct import RTStruct
from opentps.core.data._roiContour import ROIContour

from tps5d.extractor.roi_mapping import load_roi_mapping, resolve_dicom_name, RoiMapping


def _write_mapping(tmp_path, rows):
    """rows: list of (canonical_name, dicom_name) tuples."""
    path = tmp_path / "roi_mapping.csv"
    lines = ["canonical_name,dicom_name"] + [f"{c},{d}" for c, d in rows]
    path.write_text("\n".join(lines) + "\n", encoding='utf-8')
    return str(path)


def _circle_polygon(cx, cy, z, radius, n=8):
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = []
    for a in angles:
        pts += [cx + radius * np.cos(a), cy + radius * np.sin(a), z]
    return pts


def _rtstruct_with_contours(names):
    rtstruct = RTStruct(name='test')
    for name in names:
        contour = ROIContour(name=name)
        contour.polygonMesh = [_circle_polygon(10.0, 10.0, z, 5.0) for z in (0.0, 2.0, 4.0)]
        rtstruct.appendContour(contour)
    return rtstruct


class TestLoadRoiMapping:

    def test_loads_entries_and_hash(self, tmp_path):
        path = _write_mapping(tmp_path, [('Rectum', 'rectum'), ('Bladder', 'Bladder_new')])
        mapping = load_roi_mapping(path)

        assert mapping.entries == {'Rectum': 'rectum', 'Bladder': 'Bladder_new'}
        assert isinstance(mapping.content_hash, str) and len(mapping.content_hash) == 16
        assert mapping.path == path

    def test_hash_changes_when_content_changes(self, tmp_path):
        path1 = _write_mapping(tmp_path, [('Rectum', 'rectum')])
        m1 = load_roi_mapping(path1)
        path1_again = _write_mapping(tmp_path, [('Rectum', 'rectum_v2')])
        m2 = load_roi_mapping(path1_again)

        assert m1.content_hash != m2.content_hash

    def test_rejects_wrong_header(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text("name,dicom\nRectum,rectum\n", encoding='utf-8')
        with pytest.raises(ValueError, match='header'):
            load_roi_mapping(str(path))

    def test_rejects_duplicate_canonical_name(self, tmp_path):
        path = _write_mapping(tmp_path, [('Rectum', 'rectum'), ('Rectum', 'Rectum_2')])
        with pytest.raises(ValueError, match='twice'):
            load_roi_mapping(path)

    def test_skips_blank_rows(self, tmp_path):
        path = tmp_path / "sparse.csv"
        path.write_text("canonical_name,dicom_name\nRectum,rectum\n\n\n", encoding='utf-8')
        mapping = load_roi_mapping(str(path))
        assert mapping.entries == {'Rectum': 'rectum'}

    def test_empty_mapping_loads_cleanly(self, tmp_path):
        """A header-only file is a valid, intentionally unpopulated mapping:
        extractor design 9, mechanism built now, populated later.
        """
        path = tmp_path / "empty.csv"
        path.write_text("canonical_name,dicom_name\n", encoding='utf-8')
        mapping = load_roi_mapping(str(path))
        assert mapping.entries == {}


class TestResolveDicomName:

    def test_resolves_exact_match(self, tmp_path):
        path = _write_mapping(tmp_path, [('Rectum', 'Rectum')])
        mapping = load_roi_mapping(path)
        rtstruct = _rtstruct_with_contours(['Rectum', 'Bladder'])

        assert resolve_dicom_name(rtstruct, 'Rectum', mapping) == 'Rectum'

    def test_resolves_after_normalisation(self, tmp_path):
        """Mapping says 'Rectum'; the RTSTRUCT has it as ' rectum ' with
        different case and stray whitespace. Mechanical normalisation
        matches; the exact original name is what's returned, since
        getContourByName needs it verbatim.
        """
        path = _write_mapping(tmp_path, [('Rectum', 'Rectum')])
        mapping = load_roi_mapping(path)
        rtstruct = _rtstruct_with_contours([' rectum ', 'Bladder'])

        assert resolve_dicom_name(rtstruct, 'Rectum', mapping) == ' rectum '

    def test_raises_when_canonical_name_not_in_mapping(self, tmp_path):
        path = _write_mapping(tmp_path, [('Rectum', 'Rectum')])
        mapping = load_roi_mapping(path)
        rtstruct = _rtstruct_with_contours(['Rectum'])

        with pytest.raises(KeyError, match='Bladder'):
            resolve_dicom_name(rtstruct, 'Bladder', mapping)

    def test_raises_when_expected_contour_absent_from_this_struct(self, tmp_path):
        """Mapping has the entry; this particular patient's export does not
        have the structure. A different failure from the one above and the
        message must say so, since the fix is different: check the export,
        not the mapping file.
        """
        path = _write_mapping(tmp_path, [('Rectum', 'Rectum')])
        mapping = load_roi_mapping(path)
        rtstruct = _rtstruct_with_contours(['Bladder'])  # no Rectum here

        with pytest.raises(KeyError, match='data problem, not a mapping-file problem'):
            resolve_dicom_name(rtstruct, 'Rectum', mapping)

    def test_no_fuzzy_matching(self, tmp_path):
        """'Rectum' must not match 'Rectum_PRV' or similar near-misses:
        extractor design 9 rules this out explicitly.
        """
        path = _write_mapping(tmp_path, [('Rectum', 'Rectum')])
        mapping = load_roi_mapping(path)
        rtstruct = _rtstruct_with_contours(['Rectum_PRV', 'RectumWall'])

        with pytest.raises(KeyError):
            resolve_dicom_name(rtstruct, 'Rectum', mapping)
