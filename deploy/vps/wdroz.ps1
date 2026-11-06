# Z Windows: wypycha galaz na GitHub i uruchamia aktualizacje na VPS (wymaga `ssh vps4l`).
#   powershell -ExecutionPolicy Bypass -File C:\amazon-mcp\deploy\vps\wdroz.ps1 [-Galaz main] [-Ads]
# -Ads: dodatkowo przesyla ADS_API_REFRESH_TOKEN i ADS_API_PROFILE_ID z lokalnego .env do sekretow na VPS.
# Plik zapisany jako UTF-8 z BOM (PowerShell 5.1 bez BOM czyta ANSI i psuje polskie znaki).
param([string]$Galaz = "main", [switch]$Ads)
$ErrorActionPreference = "Stop"
$repo = "C:\amazon-mcp"
Set-Location $repo
if (-not (git remote | Select-String -Quiet '^origin$')) {
    git remote add origin https://github.com/wojtek80b2-ui/amazon-mcp.git
}
git push origin "${Galaz}:${Galaz}"
if ($LASTEXITCODE -ne 0) { throw "git push nie powiodl sie" }
ssh vps4l "bash /home/debian/mcp/amazon-mcp/deploy/vps/aktualizuj.sh $Galaz"
if ($LASTEXITCODE -ne 0) { throw "aktualizacja na VPS nie powiodla sie (patrz wyzej)" }
if ($Ads) {
    $linie = Select-String -Path "$repo\.env" -Pattern '^ADS_API_(REFRESH_TOKEN|PROFILE_ID|REGION)=' | ForEach-Object { $_.Line }
    if (-not $linie) { throw "Brak ADS_API_* w $repo\.env. Najpierw: python -m amazon_mcp.ads_auth" }
    ($linie -join "`n") | ssh vps4l "bash /home/debian/mcp/amazon-mcp/deploy/vps/ustaw-ads.sh"
    if ($LASTEXITCODE -ne 0) { throw "ustawienie danych Ads na VPS nie powiodlo sie" }
}
Write-Host "Gotowe."
