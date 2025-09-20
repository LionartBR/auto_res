param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string[]]$Steps = @("ETAPA_1","ETAPA_2","ETAPA_3","ETAPA_4","ETAPA_10","ETAPA_11","ETAPA_12")
)
$body = @{ steps = $Steps } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/jobs/run" -Body $body -ContentType "application/json"
$result | ConvertTo-Json -Depth 8
Write-Host "`nArquivos gerados (se houver):"
Get-ChildItem -Name Rescindidos_*.txt -ErrorAction SilentlyContinue