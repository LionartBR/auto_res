param(
  [string]$BaseUrl = "http://127.0.0.1:8000"
)
Write-Host "== Smoke =="
Invoke-WebRequest "$BaseUrl/health" | % Content
Invoke-WebRequest "$BaseUrl/version" | % Content
Write-Host "== ETAPA_1 =="
Invoke-RestMethod -Method Post "$BaseUrl/jobs/etapas/ETAPA_1" | ConvertTo-Json -Depth 5