# Build an arXiv-ready tarball of the DCP paper.
#
# Usage:
#   cd docs/paper
#   .\build-arxiv.ps1
#
# Output: docs/paper/dcp-arxiv-v0.X.tar.gz
#
# Bumps the version by reading the project version from pyproject.toml.

$ErrorActionPreference = "Stop"
$paperDir = $PSScriptRoot
Set-Location $paperDir

# Pull version from pyproject.toml for the filename.
$pyproject = Get-Content "..\..\pyproject.toml" -Raw
$version = if ($pyproject -match '(?m)^version\s*=\s*"([^"]+)"') { $matches[1] } else { "dev" }

Write-Output "=== regenerating figures ==="
python figures\make_figures.py

Write-Output "`n=== rebuilding paper (latexmk pdflatex bibtex pdflatex pdflatex) ==="
latexmk -pdf -interaction=nonstopmode main.tex | Out-Null

if (-not (Test-Path "main.pdf")) {
    Write-Error "main.pdf not produced; check main.log"
    exit 1
}
if (-not (Test-Path "main.bbl")) {
    Write-Error "main.bbl not produced; bibtex did not run"
    exit 1
}

$stage = Join-Path $env:TEMP "dcp-arxiv-staging"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Path $stage | Out-Null
New-Item -ItemType Directory -Path "$stage\figures" | Out-Null

Copy-Item main.tex $stage
Copy-Item refs.bib $stage
Copy-Item main.bbl $stage
Copy-Item figures\*.pdf "$stage\figures\"

$out = Join-Path $paperDir "dcp-arxiv-v$version.tar.gz"
if (Test-Path $out) { Remove-Item $out }
tar -czf $out -C $stage .

$size = [math]::Round((Get-Item $out).Length / 1KB, 1)
Write-Output "`n=== done ==="
Write-Output "  $out  ($size KB)"
Write-Output "  contains: main.tex, refs.bib, main.bbl, 5 figures"
Write-Output ""
Write-Output "Upload to arXiv:"
Write-Output "  1. arxiv.org -> Submit"
Write-Output "  2. Primary category: cs.NI  (or cs.DC for distributed/systems)"
Write-Output "  3. Cross-list: cs.LG (machine learning) optional"
Write-Output "  4. License: arXiv non-exclusive"
Write-Output "  5. Upload the tar.gz above; arXiv builds latex itself"
