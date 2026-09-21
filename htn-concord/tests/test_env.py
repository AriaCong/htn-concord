"""`.env` parsing -- the loader that once passed a commented key into a header."""
from __future__ import annotations

import pytest

from experiments.env import EnvError, check_value, load_env, parse_env


def test_inline_comment_is_stripped_from_an_unquoted_value():
    """The real failure: a key with a trailing comment reached an HTTP header and
    blew up 200 frames deep in urllib with a latin-1 codec error."""
    env = parse_env("OPENWEIGHT_API_KEY=gsk_abc123   # Groq 的 key\n")
    assert env["OPENWEIGHT_API_KEY"] == "gsk_abc123"


def test_a_quoted_value_keeps_its_hash():
    """A `#` can be part of a secret; quoting is how you say so."""
    assert parse_env('K="abc#def"\n')["K"] == "abc#def"
    assert parse_env("K='abc#def'\n")["K"] == "abc#def"


def test_full_line_comments_and_blanks_are_ignored():
    env = parse_env("# a comment\n\nA=1\n   # indented comment\nB=2\n")
    assert env == {"A": "1", "B": "2"}


def test_a_value_containing_equals_is_kept_whole():
    assert parse_env("K=a=b=c\n")["K"] == "a=b=c"


def test_non_ascii_in_a_key_is_rejected_by_name():
    with pytest.raises(EnvError, match="non-ASCII"):
        check_value("OPENAI_API_KEY", "sk-proj-abc的")


def test_whitespace_in_a_key_is_rejected_by_name():
    with pytest.raises(EnvError, match="whitespace"):
        check_value("OPENWEIGHT_API_KEY", "gsk_abc def")


def test_an_empty_key_is_rejected():
    with pytest.raises(EnvError, match="empty"):
        check_value("OPENAI_API_KEY", "")


def test_non_credential_values_are_not_policed():
    """Only header-bound variables are checked; a model id or a note is free."""
    check_value("OPENWEIGHT_MODEL", "openai/gpt-oss-120b")
    check_value("NOTE", "任何文字")


def test_an_exported_variable_wins_over_the_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=from-file\n")
    environ = {"OPENAI_API_KEY": "from-shell"}
    load_env(path, environ)
    assert environ["OPENAI_API_KEY"] == "from-shell"


def test_a_missing_file_is_not_an_error(tmp_path):
    assert load_env(tmp_path / "nope.env", {}) == {}


def test_load_env_raises_before_setting_a_bad_credential(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OPENWEIGHT_API_KEY=gsk_abc  # 我的 key\n")
    environ: dict[str, str] = {}
    # The comment is stripped, so this one is fine -- the guard is for what the
    # stripping cannot fix.
    load_env(path, environ)
    assert environ["OPENWEIGHT_API_KEY"] == "gsk_abc"

    path.write_text('OPENWEIGHT_API_KEY="gsk_abc 的"\n')
    with pytest.raises(EnvError):
        load_env(path, {})
