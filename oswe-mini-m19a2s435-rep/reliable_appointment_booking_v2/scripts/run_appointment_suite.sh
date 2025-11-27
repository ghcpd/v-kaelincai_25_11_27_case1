#!/usr/bin/env bash
# Shell script to run appointment suite
set -e
ROOT_DIR="$(dirname "$0")/.."
python3 $ROOT_DIR/tests/run_suite.py
