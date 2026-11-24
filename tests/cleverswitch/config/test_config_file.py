"""Tests for config/config_file.py — the config file written on the user's behalf."""

import yaml

from cleverswitch.config.config_file import DEFAULT_CONFIG, ConfigFileWriter, ensure_config_file


def test_ensure_writes_default_when_missing(tmp_path):
    path = tmp_path / "sub" / "config.yaml"
    assert ensure_config_file(path) is True
    assert yaml.safe_load(path.read_text()) == DEFAULT_CONFIG
    assert path.read_text().startswith("# CleverSwitch configuration.")


def test_ensure_leaves_existing_file_alone(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("hooks: {}\n")
    assert ensure_config_file(path) is False
    assert path.read_text() == "hooks: {}\n"


def test_ensure_swallows_write_errors(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert ensure_config_file(blocker / "config.yaml") is False
    assert "Could not create the default config" in caplog.text


def test_update_keeps_other_sections(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("hooks:\n  fire_for_all_devices: true\n")
    writer = ConfigFileWriter(path)
    assert writer.path == path
    assert writer.update(lambda raw: raw.update(host_names={1: "Notebook"})) is True
    assert yaml.safe_load(path.read_text()) == {"hooks": {"fire_for_all_devices": True}, "host_names": {1: "Notebook"}}
    assert list(tmp_path.iterdir()) == [path]  # no temp file left behind


def test_update_creates_missing_file(tmp_path):
    path = tmp_path / "config.yaml"
    assert ConfigFileWriter(path).update(lambda raw: raw.update(a=1)) is True
    assert yaml.safe_load(path.read_text()) == {"a": 1}


def test_update_refuses_to_overwrite_unparsable_file(tmp_path, caplog):
    path = tmp_path / "config.yaml"
    path.write_text("a: [unclosed\n")
    assert ConfigFileWriter(path).update(lambda raw: raw.update(a=1)) is False
    assert path.read_text() == "a: [unclosed\n"
    assert "Not saving settings" in caplog.text


def test_update_refuses_non_mapping_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("- a\n")
    assert ConfigFileWriter(path).update(lambda raw: None) is False


def test_update_reports_write_failure(tmp_path, mocker, caplog):
    path = tmp_path / "config.yaml"
    mocker.patch("cleverswitch.config.config_file.os.replace", side_effect=OSError("read-only"))
    assert ConfigFileWriter(path).update(lambda raw: raw.update(a=1)) is False
    assert "Could not save settings" in caplog.text
    assert list(tmp_path.iterdir()) == []
