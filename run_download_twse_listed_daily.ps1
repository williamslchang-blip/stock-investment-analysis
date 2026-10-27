$ErrorActionPreference = "Stop"

$stockFolderName = [string]([char]0x80A1) + [string]([char]0x5E02)
$stockDir = Join-Path (Join-Path $env:USERPROFILE "Desktop") $stockFolderName
$scriptPath = Join-Path $stockDir "download_twse_listed_close_volume.R"

Set-Location -LiteralPath $stockDir
$env:R_LIBS_USER = Join-Path $stockDir "Rlibs"

& "C:\Program Files\R\R-4.5.2\bin\Rscript.exe" $scriptPath
exit $LASTEXITCODE
