<#!
.SYNOPSIS
Smoke-test simplificado da API local do SIREP.

.DESCRIPTION
Realiza requisições básicas para validar o serviço em ``$BaseUrl`` e dispara
a execução isolada da ``ETAPA_1`` como teste rápido.
#>
param(
  [string]$BaseUrl = "http://127.0.0.1:8000"
)

Write-Host "== Smoke =="
Invoke-RestMethod -Method Get "$BaseUrl/health" | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Get "$BaseUrl/version" | ConvertTo-Json -Depth 5
Write-Host "== ETAPA_1 =="
Invoke-RestMethod -Method Post "$BaseUrl/jobs/etapas/ETAPA_1" | ConvertTo-Json -Depth 5