@rem SPDX-License-Identifier: GPL-2.0-or-later
@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-bbk9288.ps1" %*
if errorlevel 1 pause
