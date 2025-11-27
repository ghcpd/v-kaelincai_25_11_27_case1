#!/usr/bin/env bash
# Runs the pytest suite (or the python-based runner as fallback)
set -e
python -m pytest -q || python tests/run_suite.py
