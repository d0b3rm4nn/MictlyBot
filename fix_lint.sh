#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -x .venv/bin/python ]] || { echo "ERROR: falta .venv" >&2; exit 1; }
PY=".venv/bin/python"

"$PY" - << 'PYEOF'
import pathlib

edits = [
    (
        "mictlybot/app.py",
        "    otp_code_catcher,\n    otp_cmd,\n",
        "    otp_cmd,\n    otp_code_catcher,\n",
    ),
    (
        "mictlybot/otp/solver.py",
        "    profile_dir.mkdir(parents=True, exist_ok=True)\n",
        "    await asyncio.to_thread(profile_dir.mkdir, parents=True, exist_ok=True)\n",
    ),
    (
        "MictlyBotOtp(2pte).md",
        "otp_code_catcher,\\n    otp_cmd,",
        "otp_cmd,\\n    otp_code_catcher,",
    ),
    (
        "MictlyBotOtp(2pte).md",
        "    profile_dir.mkdir(parents=True, exist_ok=True)",
        "    await asyncio.to_thread(profile_dir.mkdir, parents=True, exist_ok=True)",
    ),
]

for path, old, new in edits:
    file = pathlib.Path(path)
    if not file.exists():
        print(f"  ! {path} no existe")
        continue
    text = file.read_text(encoding="utf-8")
    if old not in text:
        print(f"  = {path} (sin cambios)" if new in text else f"  ! {path}: ancla ausente")
        continue
    file.write_text(text.replace(old, new), encoding="utf-8")
    print(f"  + {path}")
PYEOF

"$PY" -m ruff check mictlybot tests
"$PY" -m ruff format --check mictlybot tests
"$PY" -m pytest tests/ -q
