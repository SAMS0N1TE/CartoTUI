<#
CartoTUI setup for Windows.
Creates a virtualenv, installs CartoTUI, and builds the native renderer if a
C compiler is available. Run from a normal PowerShell window:

    .\setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipDll,
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Find-Python {
    foreach ($cand in @(@("py","-3.12"), @("py","-3"), @("python"), @("python3"))) {
        $exe = $cand[0]
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            return $cand
        }
    }
    return $null
}

Write-Host "CartoTUI setup" -ForegroundColor Cyan
Write-Host "root: $root"

$venv = Join-Path $root "venv"
$venvPy = Join-Path $venv "Scripts\python.exe"

if ($Recreate -and (Test-Path $venv)) {
    Write-Host "Removing existing venv..."
    Remove-Item -Recurse -Force $venv
}

if (-not (Test-Path $venvPy)) {
    $py = Find-Python
    if (-not $py) {
        Write-Error "No Python found. Install Python 3.9+ from python.org and re-run."
        exit 1
    }
    Write-Host "Creating venv with: $($py -join ' ')"
    & $py[0] @($py[1..($py.Count-1)]) -m venv $venv
}

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip | Out-Null
& $venvPy -m pip install -r (Join-Path $root "requirements.txt")
& $venvPy -m pip install -e $root

if (-not $SkipDll) {
    Write-Host "Building native renderer (libcarto)..." -ForegroundColor Cyan
    $cc = $null
    foreach ($name in @("clang","gcc","cc")) {
        $c = Get-Command $name -ErrorAction SilentlyContinue
        if ($c) { $cc = $c.Source; break }
    }
    if (-not $cc) {
        $clion = Get-ChildItem "C:\Program Files\JetBrains" -Filter gcc.exe -Recurse -ErrorAction SilentlyContinue |
                 Select-Object -First 1
        if ($clion) { $cc = $clion.FullName }
    }
    if ($cc) {
        $lib = Join-Path $root "libcarto"
        $build = Join-Path $lib "build"
        New-Item -ItemType Directory -Force $build | Out-Null
        $srcs = @("style.c","framebuffer.c","raster.c","geom.c","mvt.c","carto.c") |
                ForEach-Object { Join-Path $lib "src\$_" }
        $out = Join-Path $build "carto.dll"
        Write-Host "  using $cc"
        & $cc -shared -O2 -I (Join-Path $lib "include") @srcs -o $out -lm -static-libgcc
        if (Test-Path $out) {
            Write-Host "  built $out" -ForegroundColor Green
        } else {
            Write-Warning "  DLL build failed; CartoTUI will use the slower Python renderer."
        }
    } else {
        Write-Warning "No C compiler found. Skipping native renderer; the Python renderer will be used."
        Write-Host  "  (Install LLVM/clang or mingw gcc, then re-run to enable libcarto.)"
    }
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Run CartoTUI:" -ForegroundColor Cyan
Write-Host "    .\venv\Scripts\Activate.ps1"
Write-Host "    python -m cartotui --mvt-url `"https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}`" --lat 43.2081 --lon -71.5376 --zoom 14"
Write-Host ""
Write-Host "Edit settings:" -ForegroundColor Cyan
Write-Host "    .\configure.ps1 set ui.theme dark"
Write-Host "    .\configure.ps1 themes"
