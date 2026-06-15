"""Test field_detector.py"""
import pytest
from unittest.mock import Mock
from field_detector import _normalize, _match_any, _has_value, detect_target_fields


class TestNormalize:
    def test_basic(self):
        assert _normalize("Target Start") == "target start"
        assert _normalize(None) == ""


class TestMatchAny:
    def test_match(self):
        assert _match_any("Target Start", ["target start"])


class TestHasValue:
    def test_has_value(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("KEY=val")
        assert _has_value(env.read_text(), "KEY")


class TestDetectTargetFields:
    def test_detect(self):
        class Mock:
            def get_all_fields(self):
                return [{"id": "customfield_12914", "name": "Target Start"}]
        r = detect_target_fields(Mock())
        assert r["start"] == "customfield_12914"


class TestEnsureTargetFieldIds:
    def test_writes_to_env(self, monkeypatch):
        monkeypatch.setattr("field_detector._read_env_file", lambda p: "")
        mock = Mock()
        mock.get_all_fields.return_value = [
            {"id": "customfield_12914", "name": "Target Start"}
        ]
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            env_path = os.path.join(td, ".env")
            from field_detector import ensure_target_field_ids
            result = ensure_target_field_ids(mock, env_path=env_path, reload_after=False)
            assert result["start"] == "customfield_12914"