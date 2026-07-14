<#
Convenience wrapper around "python -m cartotui.configure".
Examples:
    .\configure.ps1 list
    .\configure.ps1 set ui.theme dark
    .\configure.ps1 get render.vector_scale
    .\configure.ps1 themes
    .\configure.ps1 edit
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPy = Join-Path $root "venv\Scripts\python.exe"
$py = if (Test-Path $venvPy) { $venvPy } else { "python" }
& $py -m cartotui.configure @args
