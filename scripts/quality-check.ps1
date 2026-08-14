$ErrorActionPreference = "Stop"

Write-Host "Running POC lint and complete automated test suite..."

python -m ruff check app tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m pytest tests -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
