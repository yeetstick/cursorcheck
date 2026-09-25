import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from cursorcheck.core import Fixture


if importlib.util.find_spec("hypothesis"):
    from hypothesis import given, settings, strategies as st

    class FixtureProperties(unittest.TestCase):
        @settings(max_examples=60, deadline=None)
        @given(st.lists(st.text(alphabet="abcXYZ012-_", min_size=1, max_size=12), max_size=20, unique=True))
        def test_roundtrip_preserves_explicit_records_and_empty_pages(self, ids):
            fixture = Fixture("generated", tuple((key, "1") for key in ids), ((), tuple(ids), ()))
            path = Path(tempfile.gettempdir()) / ("cursorcheck-property-" + uuid.uuid4().hex + ".json")
            try:
                path.write_text(json.dumps(fixture.as_dict()), encoding="utf-8")
                restored = Fixture.load(path)
                self.assertEqual(restored, fixture)
                if ids:
                    with self.assertRaises(ValueError):
                        Fixture("missing", fixture.records, (tuple(ids[1:]),)).validate()
            finally:
                path.unlink(missing_ok=True)

        @settings(max_examples=100, deadline=None)
        @given(st.recursive(st.none() | st.booleans() | st.integers() | st.text(max_size=15),
                            lambda children: st.lists(children, max_size=4) |
                            st.dictionaries(st.text(max_size=12), children, max_size=4), max_leaves=20))
        def test_unstructured_json_is_rejected_with_value_error(self, value):
            path = Path(tempfile.gettempdir()) / ("cursorcheck-property-" + uuid.uuid4().hex + ".json")
            try:
                path.write_text(json.dumps(value), encoding="utf-8")
                try:
                    fixture = Fixture.load(path)
                except ValueError:
                    return
                fixture.validate()
            finally:
                path.unlink(missing_ok=True)
else:
    @unittest.skip("optional Hypothesis dependency not installed")
    class FixtureProperties(unittest.TestCase):
        def test_properties(self):
            pass
