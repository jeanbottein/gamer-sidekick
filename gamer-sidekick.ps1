# Gamer Sidekick - PowerShell Script
# Runs the main Python script with proper error handling

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "Found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.6+ from https://python.org" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Run the main script
Write-Host "Starting Gamer Sidekick..." -ForegroundColor Cyan
python gamer-sidekick.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nScript execution failed. Check the output above for errors." -ForegroundColor Red
    Read-Host "Press Enter to exit"
}
