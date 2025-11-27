# PowerShell wrapper for running integration tests
python ./mocks/mock_calendar_service.py | Out-Default &
$mockPid = $LASTEXITCODE
python ./src/app.py | Out-Default &
$apiPid = $LASTEXITCODE
Start-Sleep -Seconds 1
python ./tests/run_suite.py
Stop-Process -Id $apiPid -ErrorAction SilentlyContinue
Stop-Process -Id $mockPid -ErrorAction SilentlyContinue
