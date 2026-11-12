<#
.SYNOPSIS
  Remove exactly the files listed in a mod's install receipt (created by Install-LooseMod.ps1).

.DESCRIPTION
  A file is removed only if its current SHA-256 still matches the receipt, so files changed or
  replaced by something else are left alone and reported. Empty folders the install created under
  Data\Strings or Data\Interface are removed too. Verify afterwards with:
    python -I 05_tools\skyrim_l10n\baseline.py --game-dir "<game>" --verify 00_baseline\hashes.json
#>
param([Parameter(Mandatory = $true)] [string] $ModDir)
$ErrorActionPreference = "Stop"
$ModDir = (Resolve-Path $ModDir).Path
$receipt = Join-Path $ModDir "install_receipt.json"
if (-not (Test-Path $receipt)) { throw "No receipt at $receipt" }
# Windows PowerShell 5.1 returns a JSON array as ONE pipeline object; assign first, then enumerate.
$parsed = Get-Content -Raw $receipt | ConvertFrom-Json
$items = foreach ($entry in $parsed) { $entry }
$removed = 0; $skipped = 0
foreach ($i in $items) {
    if (-not (Test-Path -LiteralPath $i.path)) { continue }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $i.path).Hash -ne $i.sha256) {
        Write-Host "CHANGED, left in place: $($i.path)"; $skipped++; continue
    }
    Remove-Item -LiteralPath $i.path -Confirm:$false
    $removed++
}
foreach ($dir in ($items.path | ForEach-Object { Split-Path $_ } | Sort-Object -Unique)) {
    if ((Test-Path $dir) -and -not (Get-ChildItem $dir -Force)) { Remove-Item $dir -Confirm:$false }
}
if ($skipped -eq 0) { Remove-Item $receipt -Confirm:$false }
Write-Host "Removed $removed files, skipped $skipped."
