$ErrorActionPreference = "Stop"

python -m ruff check app tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m pytest tests -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
