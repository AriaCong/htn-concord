"""Read `.env` for the run scripts. No dependency, and testable.

It lives here rather than inside `scripts/run_pilot.py` because it got a
credential wrong once and cost a debugging cycle: a key with a trailing comment
was passed through verbatim into an HTTP header, and the failure surfaced as a
`UnicodeEncodeError` from deep inside `urllib` rather than as "your key has a
comment stuck to it".
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Mapping

#: Variables whose values end up in an HTTP header, so they must be clean.
_HEADER_BOUND = re.compile(r"(_API_KEY|_TOKEN)$")


class EnvError(RuntimeError):
    """A `.env` value cannot be used as given."""


def parse_env(text: str) -> dict[str, str]:
    """Parse dotenv text: `KEY=value`, `#` comments, optional quotes.

    An **unquoted** value has an inline comment stripped (` #` onwards), which is
    what every dotenv implementation does and what the commented template in
    `.env.example` invites. A quoted value keeps everything inside the quotes, so
    a `#` that is genuinely part of a secret survives when quoted.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = re.split(r"\s#", value, maxsplit=1)[0].strip()
        out[key] = value
    return out


def check_value(key: str, value: str) -> None:
    """Reject a credential that cannot survive being put in a header.

    Raises with the cause named, instead of letting `urllib` fail 200 frames
    later with a latin-1 codec error that says nothing about `.env`.
    """
    if not _HEADER_BOUND.search(key):
        return
    if not value:
        raise EnvError(f"{key} is empty.")
    bad = sorted({c for c in value if ord(c) > 127})
    if bad:
        raise EnvError(
            f"{key} contains non-ASCII character(s) {''.join(bad)!r}. "
            "A trailing comment on the same line is the usual cause: put the "
            "comment on its own line above, or quote the value."
        )
    if any(c.isspace() for c in value):
        raise EnvError(
            f"{key} contains whitespace, so it is not a bare key. "
            "Remove any trailing comment or stray text after the value."
        )
    if "#" in value:
        # An inline comment is only stripped when whitespace precedes the `#`,
        # which is the dotenv convention. A `#` glued straight to the value
        # therefore survives -- and no API key format contains one, so this is
        # always pasted junk. Catching it here beats a 401 that says only
        # "User not found".
        raise EnvError(
            f"{key} contains '#', which no API key format uses. Something is "
            "stuck to the end of the value -- usually a comment pasted without "
            "a space before the '#'. Keep only the key itself."
        )


def load_env(path: str | Path, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Load `path` into `os.environ` without overriding what is already set.

    Returns the parsed mapping. A real environment variable always wins, so an
    exported key cannot be silently shadowed by a stale file.
    """
    target = os.environ if environ is None else environ
    path = Path(path)
    if not path.exists():
        return {}
    parsed = parse_env(path.read_text(encoding="utf-8"))
    for key, value in parsed.items():
        check_value(key, value)
        target.setdefault(key, value)
    return parsed


#: Marker the HC-57 sign-off form carries once the reviewer has signed.
_SIGNED = "☑ **pass, no flags**"


def hc57_signed(signoff_path: str | Path) -> bool:
    """Has the human facts-only gate (HC-57) been signed?

    Read from the artifact rather than hardcoded, so the pilot report cannot
    claim a gate is closed after someone reverts the sign-off, and cannot keep
    stamping numbers "provisional" after it is closed.
    """
    path = Path(signoff_path)
    if not path.exists():
        return False
    return _SIGNED in path.read_text(encoding="utf-8")


def human_gate_closed(signoff_dir: str | Path, corpus_dir: str | Path) -> bool:
    """Is a signed facts-only sign-off bound to the corpus **actually on disk**?

    `hc57_signed` asks only whether the marker is present, which was enough while
    there was one corpus and one form. It is not enough once a renderer change
    rebuilds the corpus: the HC-57 signature was deliberately bound to checksums
    precisely so it would stop covering a corpus that moved underneath it, and
    nothing was checking that binding. A signed form plus a rebuilt corpus read
    as "gate closed", which is the one thing the binding existed to prevent.

    So the form has to *name* the corpus it signs off, by full SHA-256 of
    `task_b_inputs.jsonl`. Any signed form in the directory may close the gate,
    which is what lets a scoped re-read (HC-101, `hard` only) close it without
    reopening the whole 75-vignette read.

    Conservative by construction: a form that quotes its digest in truncated form
    does not match, and the gate stays open. A false "provisional" costs a label;
    a false "signed" costs the guarantee.
    """
    corpus = Path(corpus_dir) / "task_b_inputs.jsonl"
    if not corpus.exists():
        return False
    digest = hashlib.sha256(corpus.read_bytes()).hexdigest()

    directory = Path(signoff_dir)
    if not directory.is_dir():
        return False
    for form in sorted(directory.glob("*.md")):
        text = form.read_text(encoding="utf-8")
        if _SIGNED in text and digest in text:
            return True
    return False
