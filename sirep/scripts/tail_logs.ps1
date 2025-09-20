$path = Join-Path (Get-Location) "logs\sirep.log"
if (!(Test-Path $path)) { Write-Host "[tail] criando pasta logs..."; New-Item -ItemType Directory -Force -Path (Join-Path (Get-Location) "logs") | Out-Null; }
Write-Host "[tail] seguindo $path"
Get-Content -Path $path -Wait -Tail 50