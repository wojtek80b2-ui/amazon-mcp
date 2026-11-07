#!/usr/bin/env bash
# Aktualizacja serwera MCP Amazon na VPS z GitHuba (wojtek80b2-ui/amazon-mcp).
# Uruchamiać NA VPS jako debian:
#   bash /home/debian/mcp/amazon-mcp/deploy/vps/aktualizuj.sh [gałąź]      (domyślnie main)
#   bash /home/debian/mcp/amazon-mcp/deploy/vps/aktualizuj.sh --cofnij TAG  (powrót do obrazu powrot-...)
# Co robi: pobiera kod, oznacza stary obraz tagiem powrot-DATA, buduje nowy obraz,
# podmienia kontener, czeka na healthcheck; gdy kontener nie jest zdrowy, wraca do starego obrazu.
set -euo pipefail

KATALOG=/home/debian/mcp
REPO=$KATALOG/amazon-mcp
COMPOSE="docker compose -f $KATALOG/docker-compose.mcp.yml"
USLUGA=amazon-mcp
KONTENER=mcp-amazon
OBRAZ=4l-mcp/amazon

zdrowy() {  # czeka do 90 s na healthy
    local st=""
    for _ in $(seq 1 18); do
        sleep 5
        st=$(docker inspect -f '{{.State.Health.Status}}' "$KONTENER" 2>/dev/null || echo brak)
        [ "$st" = healthy ] && return 0
    done
    echo "Kontener nie jest zdrowy (stan: $st). Ostatnie logi:"; docker logs --tail 40 "$KONTENER" || true
    return 1
}

if [ "${1:-}" = "--cofnij" ]; then
    TAG=${2:?podaj tag, np. powrot-20261106-1500}
    docker image inspect "$OBRAZ:$TAG" >/dev/null
    docker image tag "$OBRAZ:$TAG" "$OBRAZ:latest"
    $COMPOSE up -d --no-build "$USLUGA"
    zdrowy && echo "Cofnięte do $OBRAZ:$TAG"
    exit $?
fi

GALAZ=${1:-main}
cd "$REPO"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "W $REPO są niezacommitowane zmiany:"; git status --short --untracked-files=no
    echo "Zachowaj je (git stash) albo odrzuć (git checkout -- PLIK) i uruchom ponownie. Przerywam."
    exit 1
fi
GIT_TERMINAL_PROMPT=0 git fetch --quiet origin
STARY=$(git rev-parse --short HEAD)
git checkout --quiet -B "$GALAZ" "origin/$GALAZ"
NOWY=$(git rev-parse --short HEAD)
echo "Kod: $STARY -> $NOWY (origin/$GALAZ)"

# Dziennik zmian reklam (ADS_CHANGE_LOG) wymaga trwałego wolumenu /dane, bo kontener jest read_only.
# Dopisywane raz do docker-compose.mcp.yml (kopia .bak-DATA); przy błędzie walidacji przywracana kopia.
PLIK_COMPOSE=$KATALOG/docker-compose.mcp.yml
if ! grep -q 'amazon_dziennik' "$PLIK_COMPOSE"; then
    KOPIA="$PLIK_COMPOSE.bak-$(date +%Y%m%d-%H%M%S)"
    cp -p "$PLIK_COMPOSE" "$KOPIA"
    if ! python3 "$REPO/deploy/vps/dziennik_compose.py" "$PLIK_COMPOSE"; then
        cp -p "$KOPIA" "$PLIK_COMPOSE"
        echo "Nie udało się dopisać wolumenu dziennika: compose bez zmian. Przerywam."; exit 1
    fi
    if $COMPOSE config -q; then
        echo "Kopia compose sprzed zmiany: $KOPIA"
    else
        cp -p "$KOPIA" "$PLIK_COMPOSE"
        echo "Compose po zmianie nie przechodzi walidacji: przywrócona kopia. Przerywam."; exit 1
    fi
fi

STAMP=$(date +%Y%m%d-%H%M)
if docker image inspect "$OBRAZ:latest" >/dev/null 2>&1; then
    docker image tag "$OBRAZ:latest" "$OBRAZ:powrot-$STAMP"
    echo "Punkt odwrotu: $OBRAZ:powrot-$STAMP"
fi

$COMPOSE build --quiet "$USLUGA"
$COMPOSE up -d "$USLUGA"
if ! zdrowy; then
    echo "POWRÓT do $OBRAZ:powrot-$STAMP"
    docker image tag "$OBRAZ:powrot-$STAMP" "$OBRAZ:latest"
    $COMPOSE up -d --no-build "$USLUGA"
    zdrowy && echo "Stary obraz działa. Nowy kod NIE został wdrożony."
    exit 1
fi
docker exec "$KONTENER" python -c "import urllib.request;print('health:',urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
echo "Wdrożone $NOWY. Stare obrazy powrot-* usuń później: docker image prune / docker rmi $OBRAZ:powrot-..."
