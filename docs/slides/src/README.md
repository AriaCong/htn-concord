# Overview deck — source

The two `.pptx` files one level up are generated, not hand-edited. Regenerate them
after editing `content.py`:

```bash
python -m venv .venv && source .venv/bin/activate    # Python 3.9+
pip install python-pptx
python build.py ..
```

- `content.py` — all copy, EN canonical + CN pair (project convention: edit both in one pass).
- `deck_lib.py` — layout primitives (palette, text, boxes, arrows).
- `build.py` — one function per slide, plus an overflow linter. The build prints
  `layout check: no overflow`; any `OVERFLOW` line means a text block is taller than
  the box holding it and the layout must be adjusted before shipping the deck.

Figures in the deck are transcribed from `HTN-Concord_Master_Plan.md`,
`HTN-Concord_Experiment_Design.md` and `benchmarks/task_b_manifest.json`. Do not
hardcode a test count anywhere — run `pytest -q`.
