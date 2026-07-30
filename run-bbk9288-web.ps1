# SPDX-License-Identifier: GPL-2.0-or-later

param(
    [ValidateRange(1, 65535)]
    [int]$HttpPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$WebSocketPort = 6081,

    [ValidateRange(1, 65535)]
    [int]$QmpPort = 6082,

    [string]$RuntimeDir,

    [string]$Nand
)

$ErrorActionPreference = "Stop"
$launcher = Join-Path $PSScriptRoot "run-bbk9288s-web.ps1"
$parameters = @{
    Machine = "bbk9288"
    HttpPort = $HttpPort
    WebSocketPort = $WebSocketPort
    QmpPort = $QmpPort
}
if (-not [string]::IsNullOrWhiteSpace($RuntimeDir)) {
    $parameters.RuntimeDir = $RuntimeDir
}
if (-not [string]::IsNullOrWhiteSpace($Nand)) {
    $parameters.Nand = $Nand
}

& $launcher @parameters
exit $LASTEXITCODE
