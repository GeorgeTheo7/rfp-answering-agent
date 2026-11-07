# Lint + tests. Exit non-zero if either fails.
$py = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$backend = Join-Path $PSScriptRoot "Backend"

& $py -m ruff check $backend
$ruff = $LASTEXITCODE

& $py -m pytest $backend
$pytest = $LASTEXITCODE
if ($pytest -eq 5) { $pytest = 0 }  # 5 = no tests collected (OK until tests exist)

if ($ruff -ne 0 -or $pytest -ne 0) { exit 1 }
exit 0
