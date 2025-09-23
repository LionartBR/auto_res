<#!
.SYNOPSIS
Executa o pipeline SIREP consumindo a API HTTP local.

.DESCRIPTION
Script auxiliar para ambientes Windows que replica o comportamento de
``python -m sirep.scripts.run_pipeline`` chamando o endpoint ``/jobs/run``.
Mantenha a lista de etapas em sincronia com ``default_step_sequence()``.
#>
param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string[]]$Steps = @(
    "ETAPA_1",
    "ETAPA_2",
    "ETAPA_3",
    "ETAPA_4",
    "ETAPA_5",
    "ETAPA_7",
    "ETAPA_8",
    "ETAPA_9",
    "ETAPA_10",
    "ETAPA_11",
    "ETAPA_12",
    "ETAPA_13"
  )
)

$body = @{ steps = $Steps } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/jobs/run" -Body $body -ContentType "application/json"
$result | ConvertTo-Json -Depth 8
Write-Host "`nArquivos gerados (se houver):"
Get-ChildItem -Name Rescindidos_*.txt -ErrorAction SilentlyContinue