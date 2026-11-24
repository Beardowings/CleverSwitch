"""Unit tests for setup/app_setup.py."""

from __future__ import annotations

import argparse

import pytest

from cleverswitch.model.context.app_context import AppContext


def _cli_args(**overrides):
    defaults = {"config": None, "verbose": False, "verbose_extra": False}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture(autouse=True)
def mock_configure_logging(mocker):
    return mocker.patch("cleverswitch.setup.app_setup.configure_logging")


@pytest.fixture(autouse=True)
def mock_ensure_config_file(mocker):
    return mocker.patch("cleverswitch.setup.app_setup.ensure_config_file")


def test_setup_context_returns_app_context(mocker):
    from cleverswitch.model.config.mouse_button_switch_config import MouseButtonSwitchConfig

    mocker.patch("cleverswitch.setup.app_setup.check")
    load = mocker.patch("cleverswitch.setup.app_setup.cfg_module.load")
    load.return_value.mouse_button_switch = MouseButtonSwitchConfig()
    mocker.patch("cleverswitch.setup.app_setup.signal.signal")

    from cleverswitch.setup.app_setup import setup_context

    ctx = setup_context(_cli_args())
    assert isinstance(ctx, AppContext)
    assert ctx.device_registry is not None
    assert ctx.topics.hid_event is not None
    assert ctx.topics.write is not None
    assert ctx.topics.device_info is not None
    assert ctx.topics.flags is not None


def test_setup_context_exits_on_config_error(mocker):
    from cleverswitch.errors.errors import ConfigError

    mocker.patch("cleverswitch.setup.app_setup.check")
    mocker.patch("cleverswitch.setup.app_setup.cfg_module.load", side_effect=ConfigError("bad"))
    mocker.patch("cleverswitch.setup.app_setup.signal.signal")

    from cleverswitch.setup.app_setup import setup_context

    with pytest.raises(SystemExit) as exc:
        setup_context(_cli_args())
    assert exc.value.code == 1


def test_config_error_configures_default_logging_before_logging_it(mocker, mock_configure_logging, caplog):
    from cleverswitch.errors.errors import ConfigError
    from cleverswitch.model.config.logging_config import LoggingConfig

    mocker.patch("cleverswitch.setup.app_setup.check")
    mocker.patch("cleverswitch.setup.app_setup.cfg_module.load", side_effect=ConfigError("bad yaml"))

    from cleverswitch.setup.app_setup import _load_config

    with caplog.at_level("ERROR"), pytest.raises(SystemExit):
        _load_config(_cli_args(verbose=True))

    mock_configure_logging.assert_called_once_with(LoggingConfig(), True)
    assert "bad yaml" in caplog.text


def test_load_config_configures_logging_from_config_before_subscribers(mocker, mock_configure_logging):
    mocker.patch("cleverswitch.setup.app_setup.check")
    mock_load = mocker.patch("cleverswitch.setup.app_setup.cfg_module.load")
    mocker.patch("cleverswitch.setup.app_setup.signal.signal")
    calls = []
    mock_configure_logging.side_effect = lambda *a: calls.append("logging")
    mocker.patch("cleverswitch.setup.app_setup._init_subscribers", side_effect=lambda *a: calls.append("subscribers"))
    mocker.patch("cleverswitch.setup.app_setup._setup_topics", side_effect=lambda: calls.append("topics"))

    from cleverswitch.setup.app_setup import setup_context

    setup_context(_cli_args(verbose_extra=True))

    mock_configure_logging.assert_called_once_with(mock_load.return_value.logging, True)
    assert calls == ["logging", "topics", "subscribers"]


def test_setup_context_initializes_subscribers(mocker):
    mocker.patch("cleverswitch.setup.app_setup.check")
    mocker.patch("cleverswitch.setup.app_setup.cfg_module.load")
    mocker.patch("cleverswitch.setup.app_setup.signal.signal")

    mock_init = mocker.patch("cleverswitch.setup.app_setup._init_subscribers")

    from cleverswitch.setup.app_setup import setup_context

    setup_context(_cli_args())
    mock_init.assert_called_once()


def test_shutdown_signal_handler_sets_event(mocker):
    mock_signal = mocker.patch("cleverswitch.setup.app_setup.signal.signal")

    from cleverswitch.setup.app_setup import _setup_shutdown

    shutdown = _setup_shutdown()
    handler = mock_signal.call_args.args[1]

    handler(15, None)

    assert shutdown.is_set()


def test_shutdown_signal_handler_skips_set_when_already_shutting_down(mocker):
    mock_signal = mocker.patch("cleverswitch.setup.app_setup.signal.signal")

    from cleverswitch.setup.app_setup import _setup_shutdown

    shutdown = _setup_shutdown()
    handler = mock_signal.call_args.args[1]
    shutdown.set()
    spy = mocker.spy(shutdown, "set")

    handler(15, None)

    spy.assert_not_called()


def test_mouse_button_switch_subscriber_always_created(mocker):
    import threading

    from cleverswitch.model.config.mouse_button_switch_config import MouseButtonSwitchConfig
    from cleverswitch.setup import app_setup

    created = mocker.patch.object(app_setup, "MouseButtonSwitchSubscriber")
    topics = app_setup._setup_topics()
    config = mocker.MagicMock()
    config.edge_switch.enabled = False
    config.mouse_button_switch = MouseButtonSwitchConfig()

    app_setup._init_subscribers(topics, mocker.MagicMock(), config, mocker.MagicMock(), threading.Event())

    created.assert_called_once()


def test_default_config_file_created_only_without_cli_path(mocker, mock_ensure_config_file):
    from cleverswitch.setup import app_setup

    mocker.patch("cleverswitch.setup.app_setup.cfg_module.load")
    mocker.patch("cleverswitch.setup.app_setup.cfg_module.default_config_path", return_value="default")

    app_setup._load_config(_cli_args())
    mock_ensure_config_file.assert_called_once_with("default")

    mock_ensure_config_file.reset_mock()
    app_setup._load_config(_cli_args(config="/x.yaml"))
    mock_ensure_config_file.assert_not_called()


def test_setup_settings_without_config_path_has_no_writer(mocker):
    from cleverswitch.model.config.config import Config
    from cleverswitch.setup import app_setup

    config = Config(hooks=mocker.MagicMock(), arguments_settings=mocker.MagicMock(), cache_path=mocker.MagicMock())
    assert app_setup._setup_settings(config, app_setup._setup_topics()).config_path is None


def test_report_flag_subscriber_follows_live_setting(mocker):
    import threading

    from cleverswitch.model.config.mouse_button_switch_config import MouseButtonSwitchConfig
    from cleverswitch.setup import app_setup

    created = mocker.patch.object(app_setup, "SetReportFlagSubscriber")
    mocker.patch.object(app_setup, "MouseButtonSwitchSubscriber")
    config = mocker.MagicMock()
    config.edge_switch.enabled = False
    config.mouse_button_switch = MouseButtonSwitchConfig()
    config.easy_switch_divert = False
    settings = mocker.MagicMock()
    settings.easy_switch_divert = True
    topics = app_setup._setup_topics()

    app_setup._init_subscribers(topics, mocker.MagicMock(), config, mocker.MagicMock(), threading.Event(), settings)
    assert created.call_args.args[2]() is True

    app_setup._init_subscribers(topics, mocker.MagicMock(), config, mocker.MagicMock(), threading.Event())
    assert created.call_args.args[2]() is False
