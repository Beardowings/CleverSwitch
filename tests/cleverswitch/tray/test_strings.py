import pytest

from cleverswitch.tray.strings import ENGLISH, GERMAN, detect_language, strings_for


@pytest.mark.parametrize("code", ["de_DE.UTF-8", "de-DE", "German_Germany", "DE"])
def test_german(code):
    assert strings_for(code) is GERMAN


@pytest.mark.parametrize("code", [None, "", "en_US", "fr_FR"])
def test_english_otherwise(code):
    assert strings_for(code) is ENGLISH


def test_both_languages_name_every_button():
    assert GERMAN.buttons.keys() == ENGLISH.buttons.keys()


def test_detect_prefers_environment():
    assert detect_language({"LANG": "de_DE.UTF-8"}, lambda: "en") == "de_DE.UTF-8"


def test_detect_skips_c_locale_and_asks_system():
    assert detect_language({"LANG": "C.UTF-8", "LC_ALL": "C"}, lambda: "de-DE") == "de-DE"


def test_detect_survives_system_lookup_failure():
    def boom():
        raise RuntimeError

    assert detect_language({}, boom) is None
