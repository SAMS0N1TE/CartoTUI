#!/usr/bin/env pwsh
# Run ASCII Map TUI (Windows PowerShell)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Join-Path $ScriptDir ".."
$Env:PYTHONPATH = "$RootDir;$Env:PYTHONPATH"

Write-Host "Launching ASCII Map..." -ForegroundColor Cyan
python -m ascii_map.cli @args
