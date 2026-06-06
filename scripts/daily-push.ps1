# daily-push.ps1
# Auto-commit + push of new/changed repo content to upstream/main (DivineSide org).
#
# Safe by design for a PUBLIC repo:
#   - Lead CSVs and local Claude state are gitignored (see .gitignore), so they never stage.
#   - A safety net below ABORTS the push if any risky file (csv / env / secret / token) slips
#     through, so a future un-ignored data file can't leak.
#
# Run manually:   pwsh -File scripts/daily-push.ps1
# Schedule daily: see the Task Scheduler one-liner in scripts/.overview.md

$ErrorActionPreference = 'Stop'

# Repo root = parent of this script's folder.
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

git add -A

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "[daily-push] No changes to push."
    exit 0
}

# Safety net: never push prospect data or secrets to the PUBLIC repo, even if un-gitignored.
$risky = $staged | Where-Object {
    $_ -match '\.csv$|\.env$|token\.json$|credentials\.json$|settings\.local\.json$|secret'
}
if ($risky) {
    Write-Warning "[daily-push] Refusing to push - risky files staged:"
    $risky | ForEach-Object { Write-Warning "  $_" }
    Write-Warning "[daily-push] Add them to .gitignore or unstage, then re-run."
    git reset | Out-Null
    exit 1
}

$date = Get-Date -Format 'yyyy-MM-dd'
git commit -m "chore: daily context sync $date"
git push upstream main

Write-Host "[daily-push] Pushed daily sync for $date ($($staged.Count) file(s))."
