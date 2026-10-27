@echo off
rem Double-click to boot Linux on the iPad 6. See boot.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0boot.ps1" %*
