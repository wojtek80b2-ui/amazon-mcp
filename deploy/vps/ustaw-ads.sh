#!/usr/bin/env bash
# Wpisuje ADS_API_REFRESH_TOKEN i ADS_API_PROFILE_ID do sekretów na VPS i restartuje mcp-amazon.
# Wartości czyta ze STDIN (linie KEY=VALUE), żeby token nie trafił do historii poleceń ani do `ps`.
# Z Windows:  Select-String '^ADS_API_(REFRESH_TOKEN|PROFILE_ID)=' C:\amazon-mcp\.env | % Line | ssh vps4l 'bash /home/debian/mcp/amazon-mcp/deploy/vps/ustaw-ads.sh'
# Na VPS:     printf 'ADS_API_REFRESH_TOKEN=...\nADS_API_PROFILE_ID=...\n' | bash deploy/vps/ustaw-ads.sh
set -euo pipefail
KATALOG=/home/debian/mcp
. "$KATALOG/.env"                      # MCP_SEKRETY
ENV="$MCP_SEKRETY/amazon.env"
[ -f "$ENV" ] || { echo "Brak $ENV"; exit 1; }

cp -p "$ENV" "$ENV.bak-$(date +%Y%m%d-%H%M)"
ile=0
while IFS= read -r linia; do
    linia=${linia%$'\r'}
    case "$linia" in
        ADS_API_REFRESH_TOKEN=*|ADS_API_PROFILE_ID=*|ADS_API_REGION=*) ;;
        "") continue ;;
        *) echo "Pomijam nieznaną linię: ${linia%%=*}"; continue ;;
    esac
    klucz=${linia%%=*}; wartosc=${linia#*=}
    [ -n "$wartosc" ] || { echo "$klucz jest puste, pomijam"; continue; }
    if grep -q "^$klucz=" "$ENV"; then
        python3 - "$ENV" "$klucz" "$wartosc" <<'PY'
import sys, re, pathlib
p, k, v = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
t = p.read_text(); t = re.sub(rf"^{re.escape(k)}=.*$", lambda m: f"{k}={v}", t, flags=re.M); p.write_text(t)
PY
    else
        printf '%s=%s\n' "$klucz" "$wartosc" >> "$ENV"
    fi
    ile=$((ile+1)); echo "Ustawione: $klucz"
done
chmod 600 "$ENV"
[ "$ile" -gt 0 ] || { echo "Nic nie ustawiono."; exit 1; }

docker compose -f "$KATALOG/docker-compose.mcp.yml" up -d amazon-mcp   # nowy env_file = nowy kontener
sleep 8
docker inspect -f 'Stan kontenera: {{.State.Health.Status}}' mcp-amazon
docker exec mcp-amazon python - <<'PY'
from amazon_mcp.ads_client import AdsClient
from amazon_mcp.config import settings
print("Brakujące dane Ads API:", AdsClient(settings).missing_credentials() or "brak, komplet")
PY
