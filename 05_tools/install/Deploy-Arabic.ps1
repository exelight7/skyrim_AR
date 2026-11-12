<#
.SYNOPSIS
  Rebuild the Arabic mod from accepted translations and (re)install it as loose files.
  Order: uninstall previous files (by receipt) -> build -> run tests -> install.
#>
param(
    [string] $Project = (Resolve-Path "$PSScriptRoot\..\..").Path,
    [string] $Python = "$env:USERPROFILE\SkyrimArabic_Tools\venv\Scripts\python.exe"
)
$ErrorActionPreference = "Stop"
$mod = Join-Path $Project "07_patch\SkyrimArabic"
if (Test-Path (Join-Path $mod "install_receipt.json")) {
    & "$PSScriptRoot\Uninstall-LooseMod.ps1" -ModDir $mod
}
# Windows PowerShell 5.1 turns any stderr line of a native program into an error record;
# judge the native steps by exit code only.
$ErrorActionPreference = "Continue"
& $Python -I "$Project\05_tools\skyrim_l10n\build_mod.py" --project $Project 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { throw "build failed" }
& $Python -I -m unittest discover -s "$Project\05_tools\tests" 2>&1 | Select-Object -Last 4 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { throw "tests failed; not installing" }
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\Install-LooseMod.ps1" -ModDir $mod
