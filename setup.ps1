<#
CartoTUI setup for Windows.
Creates a virtualenv, installs CartoTUI, and builds the native renderer if a
C compiler is available. Run from a normal PowerShell window:

    .\setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipDll,
    [switch]$SkipAdsb,
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

function Find-VsInstall {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $null }
    $path = & $vswhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath 2>$null | Select-Object -First 1
    if ($path -and (Test-Path $path)) { return $path }
    return $null
}

function Find-CMake {
    $c = Get-Command cmake -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    # Visual Studio ships its own CMake with the C++ workload.
    $vs = Find-VsInstall
    if ($vs) {
        $bundled = Join-Path $vs "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
        if (Test-Path $bundled) { return $bundled }
    }
    return $null
}

function Find-Gcc {
    foreach ($name in @("clang", "gcc", "cc")) {
        $c = Get-Command $name -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
    }
    # MSYS2 and CLion both ship a usable mingw toolchain; neither is on PATH.
    foreach ($root in @("C:\msys64\ucrt64\bin", "C:\msys64\mingw64\bin")) {
        $cand = Join-Path $root "gcc.exe"
        if (Test-Path $cand) { return $cand }
    }
    $jb = "C:\Program Files\JetBrains"
    if (Test-Path $jb) {
        $clion = Get-ChildItem $jb -Filter gcc.exe -Recurse -Depth 6 -ErrorAction SilentlyContinue |
                 Select-Object -First 1
        if ($clion) { return $clion.FullName }
    }
    return $null
}

function Build-Libcarto {
    param([string]$Root)

    $lib      = Join-Path $Root "libcarto"
    $build    = Join-Path $lib "build"
    $out      = Join-Path $build "carto.dll"
    $srcNames = @("style.c", "framebuffer.c", "raster.c", "geom.c", "mvt.c",
                  "carto.c", "cells.c")

    New-Item -ItemType Directory -Force $build | Out-Null
    if (Test-Path $out) { Remove-Item -Force $out }

    # 1. CMake covers MSVC, mingw and clang alike, and gets the DLL exports
    #    right on all three.
    $cmake = Find-CMake
    if ($cmake) {
        Write-Host "  using cmake: $cmake"
        $cm = Join-Path $build "cmake"
        & $cmake -S $lib -B $cm -DCARTO_BUILD_TESTS=OFF 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & $cmake --build $cm --config Release 2>&1 | Out-Null
            $built = Get-ChildItem $cm -Filter carto.dll -Recurse -ErrorAction SilentlyContinue |
                     Select-Object -First 1
            if ($built) {
                Copy-Item $built.FullName $out -Force
                return $out
            }
        }
        Write-Host "  cmake produced no DLL; trying a direct compile."
    }

    # 2. A gcc-alike, compiled straight. GCC exports every symbol by default.
    $cc = Find-Gcc
    if ($cc) {
        Write-Host "  using $cc"
        $srcs = $srcNames | ForEach-Object { Join-Path $lib "src\$_" }
        & $cc -shared -O2 -I (Join-Path $lib "include") @srcs -o $out -lm -static-libgcc
        if (Test-Path $out) { return $out }
    }

    # 3. MSVC directly. Unlike gcc, cl.exe exports nothing unless asked, so name
    #    the entry points the Python binding looks up.
    $vs = Find-VsInstall
    if ($vs) {
        $vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
        if (Test-Path $vcvars) {
            Write-Host "  using MSVC: $vs"
            $srcs = ($srcNames | ForEach-Object { '"' + (Join-Path $lib "src\$_") + '"' }) -join " "
            $inc  = Join-Path $lib "include"
            $exports = (@("carto_fb_init", "carto_style_default", "carto_begin",
                          "carto_render_tile", "carto_end",
                          "carto_cellify", "carto_cellify_rgb565",
                          "carto_cell_geometry") |
                        ForEach-Object { "/EXPORT:$_" }) -join " "
            $cmd = "call `"$vcvars`" >nul && cl /nologo /LD /O2 /I`"$inc`" $srcs " +
                   "/Fe:`"$out`" /Fo:`"$build\`" /link $exports"
            cmd /c $cmd 2>&1 | Out-Null
            if (Test-Path $out) { return $out }
        }
    }

    return $null
}

if (-not $SkipDll) {
    Write-Host "Building native renderer (libcarto)..." -ForegroundColor Cyan
    $dll = $null
    try {
        $dll = Build-Libcarto -Root $root
    } catch {
        Write-Warning "  native renderer build failed: $_"
    }
    if ($dll) {
        Write-Host "  built $dll" -ForegroundColor Green
    } else {
        Write-Warning "No C toolchain found, so CartoTUI falls back to the pure-Python"
        Write-Warning "renderer, which is several times slower on a busy map."
        Write-Host   "  Install any one of these, then re-run .\setup.ps1:"
        Write-Host   "    - Visual Studio Build Tools, C++ workload"
        Write-Host   "        https://aka.ms/vs/17/release/vs_BuildTools.exe"
        Write-Host   "    - MSYS2 + mingw-w64-ucrt-x86_64-gcc   https://www.msys2.org"
        Write-Host   "    - LLVM/clang                          https://releases.llvm.org"
    }
}

$interactive = -not [Console]::IsInputRedirected
if (-not $SkipAdsb -and $interactive) {
    Write-Host ""
    Write-Host "ADS-B live traffic" -ForegroundColor Cyan
    Write-Host "CartoTUI can overlay live aircraft on the map."
    Write-Host "  - No hardware? A free public feed works straight away."
    Write-Host "  - Got an SDR? setup can walk you through a local receiver."
    $ans = Read-Host "Set up ADS-B now? (Y/n)"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        & $venvPy -m cartotui.configure adsb
    } else {
        Write-Host "Skipped. Set it up later with:  .\configure.ps1 adsb"
    }
} elseif (-not $SkipAdsb) {
    Write-Host ""
    Write-Host "Skipping ADS-B setup (non-interactive shell)."
    Write-Host "Set it up later with:  .\configure.ps1 adsb"
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
Write-Host ""
Write-Host "ADS-B traffic:" -ForegroundColor Cyan
Write-Host "    .\configure.ps1 adsb                  # pick and test a source"
Write-Host "    .\configure.ps1 adsb --source api     # no hardware needed"
Write-Host "    .\configure.ps1 adsb --server-status  # local receiver + SDR status"
Write-Host "    .\configure.ps1 adsb --install-server # guided local receiver setup"
Write-Host "    .\configure.ps1 adsb --test           # re-test the saved source"
