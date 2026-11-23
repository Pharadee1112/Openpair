"""
~/.openpair/.env loading (config.load_user_env) and the test-suite home isolation.
Nothing here touches the real home folder: HOME/USERPROFILE point into tmp_path.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from openpair import ApiKeys
from openpair.config import load_user_env, user_env_path

KEY_NAMES = ("GROQ_API_KEY", "GOOGLE_API_KEY", "OLLAMA_MODEL")


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / ".openpair").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    for n in KEY_NAMES:
        monkeypatch.delenv(n, raising=False)
    return h


def write_user_env(home: Path, text: str) -> None:
    (home / ".openpair" / ".env").write_text(text, encoding="utf-8")


def test_conftest_isolates_the_home_folder(_isolated_home):
    assert Path.home() == _isolated_home
    assert "home" in _isolated_home.name
    assert user_env_path() == Path.home() / ".openpair" / ".env"


def test_loads_values_into_environment(home):
    write_user_env(home, "GROQ_API_KEY=gsk_user\nGOOGLE_API_KEY='g-user'\n# comment\n")
    load_user_env()
    assert os.environ["GROQ_API_KEY"] == "gsk_user"
    assert os.environ["GOOGLE_API_KEY"] == "g-user"
    assert ApiKeys().groq == "gsk_user"


def test_real_environment_variable_wins(home, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "from-real-env")
    write_user_env(home, "GROQ_API_KEY=from-user-file\n")
    load_user_env()
    assert os.environ["GROQ_API_KEY"] == "from-real-env"


@pytest.mark.parametrize("empty", ["", "   "])
def test_empty_value_counts_as_unset(home, monkeypatch, empty):
    monkeypatch.setenv("GROQ_API_KEY", empty)
    write_user_env(home, "GROQ_API_KEY=from-user-file\n")
    load_user_env()
    assert os.environ["GROQ_API_KEY"] == "from-user-file"


def test_empty_value_in_user_file_sets_nothing(home):
    write_user_env(home, "GROQ_API_KEY=\n")
    load_user_env()
    assert "GROQ_API_KEY" not in os.environ


def test_missing_or_unreadable_file_is_silent(home):
    load_user_env()                                     # no file
    (home / ".openpair" / ".env").write_bytes(b"\xff\xfe\x00bad\x80")
    load_user_env()                                     # not UTF-8
    load_user_env(home / "does-not-exist")
    assert "GROQ_API_KEY" not in os.environ


def run_import(cwd: Path, home: Path, extra_env: dict) -> str:
    """Import openpair.config in a fresh interpreter (import is when the .env files load)."""
    env = {k: v for k, v in os.environ.items() if k not in KEY_NAMES}
    env.update(HOME=str(home), USERPROFILE=str(home), **extra_env)
    code = "import openpair.config, os; print(os.environ.get('GROQ_API_KEY', '<none>'))"
    out = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True,
                         text=True, timeout=120, check=True)
    return out.stdout.strip()


def test_import_precedence_env_then_cwd_then_user_file(tmp_path, home):
    # openpair must be importable from the empty cwd (it is installed, not found via cwd)
    cwd = tmp_path / "proj"
    cwd.mkdir()
    write_user_env(home, "GROQ_API_KEY=user-file\n")

    assert run_import(cwd, home, {}) == "user-file"                      # only the user file
    (cwd / ".env").write_text("GROQ_API_KEY=cwd-file\n", encoding="utf-8")
    assert run_import(cwd, home, {}) == "cwd-file"                       # cwd .env beats it
    assert run_import(cwd, home, {"GROQ_API_KEY": "real-env"}) == "real-env"   # env beats both
    (cwd / ".env").write_text("GROQ_API_KEY=\n", encoding="utf-8")
    assert run_import(cwd, home, {}) == "user-file"                      # empty cwd line = unset
