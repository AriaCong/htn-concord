#!/bin/sh
# Run from anywhere: cleans NHANES I+J, then independently verifies the outputs.
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
uv run --no-project --with pandas==2.2.3 --with numpy python -I "$here/clean_nhanes_ij.py"
uv run --no-project --with pandas==2.2.3 --with numpy python -I "$here/verify.py"
uv run --no-project --with pandas==2.2.3 --with numpy python -I "$here/export_model_input.py"
uv run --no-project --with pandas==2.2.3 --with numpy --with openpyxl python "$here/compute_prevent.py"
