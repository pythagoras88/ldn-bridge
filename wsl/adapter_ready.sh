#!/usr/bin/env bash
# Run IN WSL, no sudo: exit 0 if the USB adapter from config.toml has a working driver (a phy), else print why and exit 1.
cd "$(dirname "$(readlink -f "$0")")/.."
exec .venv/bin/python -c 'import sys
sys.path.insert(0, "src")
from ldn_bridge import adapter, config
print("Adapter ready on", adapter.find_phy(config.load().adapter_mac))'
