"""`.env` parsing -- the loader that once passed a commented key into a header."""
from __future__ import annotations

import hashlib

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


def test_hc57_gate_is_read_from_the_artifact_not_hardcoded(tmp_path):
    """The report must not claim a gate is closed on its own say-so."""
    from experiments.env import hc57_signed

    path = tmp_path / "signoff.md"
    assert hc57_signed(path) is False           # missing file

    path.write_text("- **Outcome:** ☐ pass, no flags ☐ fail\n")
    assert hc57_signed(path) is False           # present but unsigned

    path.write_text("- **Outcome:** ☑ **pass, no flags** ☐ fail\n")
    assert hc57_signed(path) is True


def test_the_real_signoff_form_reads_as_signed():
    """Pins the marker against the actual artifact, so a reformat of the form
    cannot silently flip the pilot report back to 'provisional'."""
    from pathlib import Path

    from experiments.env import hc57_signed

    form = (Path(__file__).resolve().parents[2] / "docs" / "signoffs"
            / "HC-57_facts-only_spotcheck_signoff.md")
    assert form.exists(), form
    assert hc57_signed(form) is True


def test_a_hash_glued_to_a_key_is_rejected_rather_than_sent():
    """Real failure: a comment pasted with no space before the '#' survived the
    dotenv comment rule, went out in the Authorization header, and came back as
    a bare 401 'User not found' that said nothing about .env."""
    with pytest.raises(EnvError, match="#"):
        check_value("OPENWEIGHT_API_KEY", "sk-or-v1-abc123#note_pasted_here")


def test_a_whitespace_separated_comment_is_still_just_stripped():
    """The convention still holds; only the glued case is an error."""
    env = parse_env("OPENWEIGHT_API_KEY=sk-or-v1-abc123   # a note\n")
    assert env["OPENWEIGHT_API_KEY"] == "sk-or-v1-abc123"
    check_value("OPENWEIGHT_API_KEY", env["OPENWEIGHT_API_KEY"])


def test_human_gate_is_not_closed_by_a_signature_bound_to_a_different_corpus(tmp_path):
    """HC-101: a signed form only closes the gate for the corpus it names.

    `hc57_signed` asks one question -- is the marker present? -- so any signed
    form kept the numbers non-provisional even after the corpus underneath it
    was rebuilt. That is the failure the HC-57 signature was deliberately bound
    to checksums to prevent, and nothing was checking the binding.

    Erring toward "provisional" is the safe direction, so a form that does not
    name the corpus digest in full does not close the gate.
    """
    from experiments.env import human_gate_closed

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    inputs = corpus / "task_b_inputs.jsonl"
    inputs.write_text('{"case_id": "taskb-1-simple"}\n', encoding="utf-8")
    digest = hashlib.sha256(inputs.read_bytes()).hexdigest()

    signoffs = tmp_path / "signoffs"
    signoffs.mkdir()

    signed_other = signoffs / "HC-57_facts-only_spotcheck_signoff.md"
    signed_other.write_text("Outcome: ☑ **pass, no flags**\ncorpus `deadbeef`\n",
                            encoding="utf-8")
    assert human_gate_closed(signoffs, corpus) is False, \
        "a signature naming another corpus must not close the gate"

    unsigned_match = signoffs / "HC-101_hard-level_rereview_signoff.md"
    unsigned_match.write_text(f"Outcome: ☐ pass, no flags\ncorpus `{digest}`\n",
                              encoding="utf-8")
    assert human_gate_closed(signoffs, corpus) is False, \
        "naming the corpus is not enough; the form must also be signed"

    unsigned_match.write_text(f"Outcome: ☑ **pass, no flags**\ncorpus `{digest}`\n",
                              encoding="utf-8")
    assert human_gate_closed(signoffs, corpus) is True
