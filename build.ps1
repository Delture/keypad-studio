$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

& ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed `
  --name KeypadStudio --icon assets/icon.ico `
  --add-data "web;web" --add-data "assets;assets" `
  --collect-all webview --collect-all pythonnet --collect-all clr_loader --collect-all hid `
  --collect-all pycaw --collect-all comtypes --collect-all psutil `
  --hidden-import webview.platforms.edgechromium app.py

Write-Host "Built: $PSScriptRoot\dist\KeypadStudio"
