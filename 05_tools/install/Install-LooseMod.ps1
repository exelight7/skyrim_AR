<#
.SYNOPSIS
  Copy a mod folder's files into Skyrim's Data folder as NEW loose files only.

.DESCRIPTION
  - Refuses to run if ANY target file already exists (never overwrites game or other mod files).
  - Writes a receipt (paths + SHA-256) next to the mod so Uninstall-LooseMod.ps1 can remove exactly
    these files and nothing else.
  - Original BSA/ESM files are never touched; loose files simply take priority over BSA contents.

.EXAMPLE
  .\Install-LooseMod.ps1 -ModDir "..\..\07_patch\SkyrimArabic_RenderTest"
#>
param(
    [Parameter(Mandatory = $true)] [string] $ModDir,
    # Game moved to the E: Steam library on 2026-11-10 (same build 24914197 / 1.7.104).
    [string] $GameData = "E:\SteamLibrary\steamapps\common\Skyrim Special Edition\Data",
    [string[]] $Include = @("Strings", "Interface")
)
$ErrorActionPreference = "Stop"
$ModDir = (Resolve-Path $ModDir).Path
$receipt = Join-Path $ModDir "install_receipt.json"
if (Test-Path $receipt) { throw "Receipt exists ($receipt): already installed. Uninstall first." }

$files = foreach ($sub in $Include) {
    $root = Join-Path $ModDir $sub
    if (Test-Path $root) { Get-ChildItem $root -Recurse -File }
}
$plan = foreach ($f in $files) {
    $rel = $f.FullName.Substring($ModDir.Length).TrimStart('\')
    [pscustomobject]@{ Source = $f.FullName; Target = (Join-Path $GameData $rel); Rel = $rel }
}
$conflicts = $plan | Where-Object { Test-Path $_.Target }
if ($conflicts) {
    $conflicts | ForEach-Object { Write-Host "EXISTS: $($_.Target)" }
    throw "Aborted: $(@($conflicts).Count) target file(s) already exist. Nothing was copied."
}

$installed = @()
foreach ($p in $plan) {
    New-Item -ItemType Directory -Force -Path (Split-Path $p.Target) | Out-Null
    Copy-Item -LiteralPath $p.Source -Destination $p.Target
    $installed += [pscustomobject]@{ path = $p.Target; sha256 = (Get-FileHash -Algorithm SHA256 $p.Target).Hash }
}
$installed | ConvertTo-Json | Set-Content -Encoding UTF8 $receipt
Write-Host "Installed $($installed.Count) files. Receipt: $receipt"
