#!/usr/bin/env bash
# Minimal environment setup for Unix/WSL environments. For Windows, run similar steps in powershell.
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
