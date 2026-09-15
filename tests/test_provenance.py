"""Tests for extractor.provenance."""

import pytest

from tps5d.extractor.provenance import ProvenanceRecord, ProvenanceTable, KINDS


def _record(key='dose:pt12/b1/PT-A/planned', kind='measured',
           source='RayStation Eclipse-AAA', content_hash='abc123'):
    return ProvenanceRecord(key=key, kind=kind, source=source, content_hash=content_hash)


class TestProvenanceRecord:

    def test_accepts_every_declared_kind(self):
        for kind in KINDS:
            r = _record(kind=kind)
            assert r.kind == kind

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match='kind must be one of'):
            _record(kind='guessed')

    def test_rejects_empty_key(self):
        with pytest.raises(ValueError, match='key must not be empty'):
            _record(key='')

    def test_rejects_empty_source(self):
        with pytest.raises(ValueError, match='source must not be empty'):
            _record(source='')

    def test_is_frozen(self):
        r = _record()
        with pytest.raises(Exception):
            r.key = 'something else'


class TestProvenanceTableAddGet:

    def test_add_then_get_round_trips(self):
        table = ProvenanceTable()
        r = _record()
        table.add(r)
        assert table.get(r.key) == r

    def test_add_raises_on_duplicate_key(self):
        table = ProvenanceTable()
        table.add(_record(key='dose:pt1/b1/PT-A/planned'))
        with pytest.raises(KeyError, match='already recorded'):
            table.add(_record(key='dose:pt1/b1/PT-A/planned', source='different source'))

    def test_get_raises_on_missing_key(self):
        table = ProvenanceTable()
        with pytest.raises(KeyError, match='no provenance recorded'):
            table.get('nothing:here')

    def test_update_overwrites_without_raising(self):
        table = ProvenanceTable()
        table.add(_record(key='k', content_hash='old'))
        table.update(_record(key='k', content_hash='new'))
        assert table.get('k').content_hash == 'new'

    def test_update_also_works_for_a_brand_new_key(self):
        table = ProvenanceTable()
        table.update(_record(key='k'))
        assert table.get('k').key == 'k'

    def test_len_and_contains(self):
        table = ProvenanceTable()
        assert len(table) == 0
        assert 'k' not in table
        table.add(_record(key='k'))
        assert len(table) == 1
        assert 'k' in table


class TestProvenanceTableQuery:

    def _populated(self):
        table = ProvenanceTable()
        table.add(_record(key='dose:pt1/b1', kind='measured', source='RayStation'))
        table.add(_record(key='ntcp:rectum_n', kind='assumed', source='X9'))
        table.add(_record(key='ntcp:rectum_td50', kind='published', source='Michalski 2010 QUANTEC'))
        table.add(_record(key='facility:cap_xt_min_day', kind='swept', source='A13'))
        return table

    def test_query_with_no_filter_returns_everything_sorted_by_key(self):
        table = self._populated()
        keys = [r.key for r in table.query()]
        assert keys == sorted(keys)
        assert len(keys) == 4

    def test_query_by_kind_is_the_enumerability_requirement(self):
        """This is the concrete case extractor design 13 exists for:
        listing every assumed parameter by query, not by hand.
        """
        table = self._populated()
        assumed = table.query(kind='assumed')
        assert [r.key for r in assumed] == ['ntcp:rectum_n']

    def test_query_by_kind_with_none_present_returns_empty_not_an_error(self):
        table = ProvenanceTable()
        table.add(_record(kind='measured'))
        assert table.query(kind='swept') == []

    def test_query_rejects_unknown_kind(self):
        table = self._populated()
        with pytest.raises(ValueError, match='kind must be one of'):
            table.query(kind='guessed')

    def test_iteration_matches_query_with_no_filter(self):
        table = self._populated()
        assert list(table) == table.query()


class TestProvenanceTableCsvRoundTrip:

    def test_write_then_read_round_trips_every_field(self, tmp_path):
        table = self._make_populated_table()
        path = str(tmp_path / 'provenance.csv')
        table.write_csv(path)

        loaded = ProvenanceTable.read_csv(path)

        assert len(loaded) == len(table)
        for record in table.query():
            assert loaded.get(record.key) == record

    def _make_populated_table(self):
        table = ProvenanceTable()
        table.add(_record(key='dose:pt1/b1', kind='measured', source='RayStation'))
        table.add(_record(key='ntcp:rectum_n', kind='assumed', source='X9'))
        return table

    def test_read_csv_rejects_wrong_header(self, tmp_path):
        path = tmp_path / 'bad.csv'
        path.write_text('key,kind,source\nk,measured,src\n', encoding='utf-8')
        with pytest.raises(ValueError, match='header'):
            ProvenanceTable.read_csv(str(path))

    def test_read_csv_raises_on_duplicate_key_same_as_add_would(self, tmp_path):
        path = tmp_path / 'dup.csv'
        path.write_text(
            'key,kind,source,content_hash\n'
            'k,measured,src,h1\n'
            'k,measured,src,h2\n',
            encoding='utf-8',
        )
        with pytest.raises(KeyError, match='already recorded'):
            ProvenanceTable.read_csv(str(path))

    def test_empty_table_writes_a_header_only_file(self, tmp_path):
        table = ProvenanceTable()
        path = str(tmp_path / 'empty.csv')
        table.write_csv(path)

        loaded = ProvenanceTable.read_csv(path)
        assert len(loaded) == 0
