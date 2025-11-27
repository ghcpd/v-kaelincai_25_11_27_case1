# PowerShell version of runner
python -m pytest -q; if ($LASTEXITCODE -ne 0) { python tests/run_suite.py }
