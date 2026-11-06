# Z Windows: wypycha gałąź na GitHub i uruchamia aktualizację na VPS (wymaga `ssh vps4l`).
#   powershell -ExecutionPolicy Bypass -File C:\amazon-mcp\deploy\vps\wdroz.ps1 [-Galaz main] [-Ads]
# -Ads: dodatkowo przesyła ADS_API_REFRESH_TOKEN i ADS_API_PROFILE_ID z lokalnego .env do sekretów na VPS.
param([string]$Galaz = "main", [switch]$Ads)
$ErrorActionPreference = "Stop"
$repo = "C:\amazon-mcp"
Set-Location $repo
if (-not (git remote | Select-String -Quiet '^origin$')) {
    git remote add origin https://github.com/wojtek80b2-ui/amazon-mcp.git
}
git push origin "${Galaz}:${Galaz}"
if ($LASTEXITCODE -ne 0) { throw "git push nie powiódł się" }
ssh vps4l "bash /home/debian/mcp/amazon-mcp/deploy/vps/aktualizuj.sh $Galaz"
if ($LASTEXITCODE -ne 0) { throw "aktualizacja na VPS nie powiodła się (patrz wyżej)" }
if ($Ads) {
    $linie = Select-String -Path "$repo\.env" -Pattern '^ADS_API_(REFRESH_TOKEN|PROFILE_ID|REGION)=' | ForEach-Object Line
    if (-not $linie) { throw "Brak ADS_API_* w $repo\.env — najpierw: python -m amazon_mcp.ads_auth" }
    $linie -join "`n" | ssh vps4l "bash /home/debian/mcp/amazon-mcp/deploy/vps/ustaw-ads.sh"
}
