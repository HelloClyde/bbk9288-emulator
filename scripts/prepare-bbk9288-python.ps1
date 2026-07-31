param(
    [Parameter(Mandatory)]
    [string]$OutputDir,

    [string]$Requirements = ".\requirements-bbk9288.txt",

    [string]$BuildPython = "python",

    [string]$ArchiveUrl = (
        "https://www.python.org/ftp/python/3.13.11/" +
        "python-3.13.11-embeddable-amd64.zip"
    ),

    [string]$ArchiveSha256 = (
        "73a9e5629ebbb91877be94b80b51139b2bbd39f83360b9b2f8a745627919e070"
    )
)

$ErrorActionPreference = "Stop"
$output = [System.IO.Path]::GetFullPath($OutputDir)
$requirementsPath = [System.IO.Path]::GetFullPath($Requirements)
$parent = [System.IO.Path]::GetDirectoryName($output)
$archive = Join-Path $parent (
    "python-embed-" + [System.Guid]::NewGuid().ToString("N") + ".zip"
)

if (Test-Path -LiteralPath $output) {
    throw "Portable Python output already exists: $output"
}
if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    throw "Python requirements are missing: $requirementsPath"
}

New-Item -ItemType Directory -Path $parent -Force | Out-Null

try {
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $archive
    $actualHash = (
        Get-FileHash -LiteralPath $archive -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($actualHash -ne $ArchiveSha256.ToLowerInvariant()) {
        throw (
            "Portable Python archive hash mismatch: expected " +
            "$ArchiveSha256, got $actualHash"
        )
    }

    Expand-Archive -LiteralPath $archive -DestinationPath $output
    $sitePackages = Join-Path $output "Lib\site-packages"
    New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null

    & $BuildPython -m pip install `
        --disable-pip-version-check `
        --requirement $requirementsPath `
        --target $sitePackages
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install portable Python dependencies"
    }

    $pth = Get-ChildItem -LiteralPath $output -Filter "python*._pth" |
        Select-Object -First 1
    if (-not $pth) {
        throw "Portable Python path configuration is missing"
    }
    $pthLines = @(
        Get-Content -LiteralPath $pth.FullName |
            Where-Object {
                $_ -notin @("Lib\site-packages", "..\scripts")
            }
    )
    $pthLines += "Lib\site-packages"
    $pthLines += "..\scripts"
    Set-Content -LiteralPath $pth.FullName -Value $pthLines -Encoding ascii

    $portablePython = Join-Path $output "python.exe"
    & $portablePython -c "import pyfatfs, fs"
    if ($LASTEXITCODE -ne 0) {
        throw "Portable Python dependency validation failed"
    }
} finally {
    if (Test-Path -LiteralPath $archive -PathType Leaf) {
        Remove-Item -LiteralPath $archive
    }
}

Write-Host "Portable Python: $output"
