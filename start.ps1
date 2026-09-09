$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    throw 'Please follow README.md to install the project environment first.'
}
& './.venv/Scripts/python.exe' launch.py
