#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .build
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if [[ ! -f .venv/requirements.installed ]] || ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install --index-url https://pypi.org/simple --no-cache-dir -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
if [[ ! -x .build/PenBridge || native/PenBridge.swift -nt .build/PenBridge ]]; then
  swiftc -module-cache-path .build/module-cache native/PenBridge.swift -o .build/PenBridge
fi
exec .venv/bin/python server.py "$@"
