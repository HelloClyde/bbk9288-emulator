# SPDX-License-Identifier: GPL-2.0-or-later

param(
    [string]$Nand,
    [string]$Qemu,
    [string]$AudioPlayer,
    [string]$OutputDir,
    [switch]$KeepTestNand,
    [ValidateRange(5, 120)]
    [int]$Seconds = 8
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Nand)) {
    $Nand = @(
        (Join-Path $PSScriptRoot "..\runtime\nand-user.raw"),
        (Join-Path $PSScriptRoot "..\nand-user.raw"),
        (Join-Path $PSScriptRoot "..\..\BBK9288模拟器\nand-user.raw")
    ) | Where-Object {
        Test-Path -LiteralPath $_ -PathType Leaf
    } | Select-Object -First 1
}
if ([string]::IsNullOrWhiteSpace($Nand)) {
    throw "找不到 9288 NAND；请用 -Nand 指定 nand-user.raw。"
}

$arguments = @(
    (Join-Path $PSScriptRoot "test-bbk9288.py"),
    "--nand", $Nand,
    "--seconds", $Seconds
)
if (-not [string]::IsNullOrWhiteSpace($Qemu)) {
    $arguments += @("--qemu", $Qemu)
}
if (-not [string]::IsNullOrWhiteSpace($AudioPlayer)) {
    $arguments += @("--audio-player", $AudioPlayer)
}
if (-not [string]::IsNullOrWhiteSpace($OutputDir)) {
    $arguments += @("--output-dir", $OutputDir)
}
if ($KeepTestNand) {
    $arguments += "--keep-test-nand"
}

& python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "BBK 9288 自动回归测试失败，退出码 $LASTEXITCODE。"
}
