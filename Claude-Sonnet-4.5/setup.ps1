# Setup script for Windows (PowerShell)
# Appointment Booking System Setup

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Appointment Booking System Setup" -ForegroundColor Cyan
Write-Host "Reliable_Appointment_Booking_v2" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ProjectRoot = $PSScriptRoot

Write-Host "Project Root: $ProjectRoot" -ForegroundColor Yellow
Write-Host ""

# Check Python
Write-Host "Checking Python installation..." -ForegroundColor Yellow
$pythonCmd = $null

if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} else {
    Write-Host "Python not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.8 or higher from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

Write-Host "Python found: $pythonCmd" -ForegroundColor Green
& $pythonCmd --version
Write-Host ""

# Check pip
Write-Host "Checking pip..." -ForegroundColor Yellow
$pipCheck = & $pythonCmd -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip not found!" -ForegroundColor Red
    Write-Host "Please install pip: $pythonCmd -m ensurepip --upgrade" -ForegroundColor Red
    exit 1
}

Write-Host "pip found" -ForegroundColor Green
Write-Host $pipCheck
Write-Host ""

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
if (Test-Path "requirements.txt") {
    & $pythonCmd -m pip install -q -r requirements.txt
    Write-Host "Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "requirements.txt not found, installing minimal dependencies..." -ForegroundColor Yellow
    & $pythonCmd -m pip install -q pyyaml
}
Write-Host ""

# Create directories
Write-Host "Creating directory structure..." -ForegroundColor Yellow
$dirs = @(
    "logs",
    "tests\integration",
    "mocks",
    "src\appointment",
    "src\adapters",
    "frontend\static",
    "docs\screenshots",
    "scripts"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

Write-Host "Directories created" -ForegroundColor Green
Write-Host ""

# Verify structure
Write-Host "Verifying project structure..." -ForegroundColor Yellow
$requiredFiles = @(
    "src\appointment\state_machine.py",
    "src\appointment\idempotency.py",
    "src\appointment\saga.py",
    "src\appointment\database.py",
    "src\appointment\audit_logger.py",
    "src\appointment\controller.py",
    "src\adapters\calendar_adapter.py",
    "mocks\mock_calendar_service.py",
    "tests\run_suite.py",
    "tests\integration\appointment_cases.yaml",
    "frontend\index.html",
    "logs\audit_schema.json"
)

$missingFiles = 0
foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        Write-Host "Missing: $file" -ForegroundColor Red
        $missingFiles++
    }
}

if ($missingFiles -eq 0) {
    Write-Host "All required files present" -ForegroundColor Green
} else {
    Write-Host "$missingFiles file(s) missing" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SETUP COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Run tests: .\run_tests.ps1" -ForegroundColor White
Write-Host "  2. Open frontend: start frontend\index.html" -ForegroundColor White
Write-Host "  3. View docs: docs\root_cause_analysis.md" -ForegroundColor White
Write-Host ""
