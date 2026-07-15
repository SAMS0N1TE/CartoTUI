<#
Convenience wrapper around "python -m cartotui.configure".
Examples:
    .\configure.ps1 list
    .\configure.ps1 set ui.theme dark
    .\configure.ps1 get render.vector_scale
    .\configure.ps1 themes
    .\configure.ps1 edit

ADS-B live traffic:
    .\configure.ps1 adsb                                   # interactive wizard
    .\configure.ps1 adsb --test                            # probe the saved source
    .\configure.ps1 adsb --list-ports                      # show serial ports
    .\configure.ps1 adsb --source sbs1 --host 192.168.1.50 # dump1090 over TCP
    .\configure.ps1 adsb --source api --provider adsb.lol  # online feed
    .\configure.ps1 adsb --disable
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPy = Join-Path $root "venv\Scripts\python.exe"
$py = if (Test-Path $venvPy) { $venvPy } else { "python" }
& $py -m cartotui.configure @args
