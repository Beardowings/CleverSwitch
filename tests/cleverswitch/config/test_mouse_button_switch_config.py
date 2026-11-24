"""Parsing of the mouse_button_switch config section."""

from __future__ import annotations

import argparse

import pytest

from cleverswitch.config.config import _parse
from cleverswitch.model.config.mouse_button_switch_config import MouseButtonSwitchConfig


def _cli_args() -> argparse.Namespace:
    return argparse.Namespace(config=None, verbose_extra=None)


def _mbs(section) -> MouseButtonSwitchConfig:
    return _parse({"mouse_button_switch": section}, _cli_args()).mouse_button_switch


def test_missing_section_is_disabled():
    assert _parse({}, _cli_args()).mouse_button_switch == MouseButtonSwitchConfig()


def test_minimal_section_uses_gesture_button():
    assert _mbs({"host": 2}) == MouseButtonSwitchConfig(enabled=True, cid=0x00C3, target_host=1, divert=True)


@pytest.mark.parametrize(
    ("button", "cid"),
    [("gesture", 0x00C3), ("Forward", 0x0056), ("back", 0x0053), ("0x00c4", 0x00C4), (0x0052, 0x0052)],
)
def test_button_names_and_numbers(button, cid):
    assert _mbs({"host": 1, "button": button}).cid == cid


@pytest.mark.parametrize("button", ["thumb", True, 0, 0x10000, "-1"])
def test_invalid_button_disables(button, caplog):
    assert _mbs({"host": 1, "button": button}).enabled is False


@pytest.mark.parametrize("host", [None, 0, 4, "2", True])
def test_invalid_host_disables(host):
    section = {} if host is None else {"host": host}
    assert _mbs(section).enabled is False


def test_divert_false_listens_only():
    assert _mbs({"host": 3, "divert": False}).divert is False


def test_invalid_divert_falls_back_to_true(caplog):
    assert _mbs({"host": 3, "divert": "no"}).divert is True
    assert "'divert'" in caplog.text


def test_enabled_false_disables():
    assert _mbs({"host": 2, "enabled": False}).enabled is False


def test_invalid_enabled_disables(caplog):
    assert _mbs({"host": 2, "enabled": "yes"}).enabled is False


def test_non_mapping_disables(caplog):
    assert _mbs("on") == MouseButtonSwitchConfig()
    assert "must be a mapping" in caplog.text


def test_unknown_key_warns(caplog):
    assert _mbs({"host": 2, "hots": 1}).enabled is True
    assert "unknown key 'hots'" in caplog.text
