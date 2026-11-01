#!/usr/bin/env bash
# Run ON THE DECK, no sudo: creates .venv and installs the ldn library + this project.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
"$PY" - <<'EOF'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"Python {sys.version.split()[0]} found; need 3.11+. Install a newer Python, or use Distrobox.")
print("Python", sys.version.split()[0], "OK")
EOF

# --copies: the venv gets its own python binary, so grant_caps.sh can setcap it without touching system python.
"$PY" -m venv --copies .venv
# grant_caps.sh setcaps python3 only, but activate runs bin/python, so every name must be that one file.
for f in .venv/bin/python .venv/bin/python3.*; do ln -sf python3 "$f"; done
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "https://github.com/kinnay/LDN/archive/refs/heads/master.zip"
python -m pip install -e .
python -c "import ldn, trio; print('ldn library OK')"
echo
echo "Next: sudo bash deck/grant_caps.sh, then cp config.example.toml config.toml and edit it."
