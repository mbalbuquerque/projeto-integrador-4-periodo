#!/usr/bin/env bash
# Mede em quanto tempo a API volta a responder depois de o contêiner morrer.
# Uso: medir_reinicio.sh <saida.txt>   (compose já no ar; só para o CI)
set -u
SAIDA="${1:-reinicio.txt}"
URL="http://localhost:7071/api/health"
: > "$SAIDA"
log() { echo "$*" | tee -a "$SAIDA"; }

esperar_200() {  # imprime os segundos até /api/health responder 200 (teto 180 s)
  local t0=$1 agora
  while true; do
    agora=$(date +%s.%N)
    if [ "$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$URL")" = "200" ]; then
      echo "$(date +%s.%N) - $t0" | bc; return 0
    fi
    if (( $(echo "$agora - $t0 > 180" | bc) )); then echo "TIMEOUT"; return 1; fi
    sleep 0.5
  done
}

ID=$(docker compose -f infra/docker-compose.yml ps -q api)
log "contêiner: $ID"
log "política de reinício: $(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$ID")"
log "saúde antes: $(docker inspect -f '{{.State.Health.Status}}' "$ID")"

for modo in "docker kill" "kill -9 do PID 1 dentro do contêiner"; do
  n_antes=$(docker inspect -f '{{.RestartCount}}' "$ID")
  t0=$(date +%s.%N)
  if [ "$modo" = "docker kill" ]; then docker kill "$ID" >/dev/null; else docker exec "$ID" kill -9 1 >/dev/null 2>&1; fi
  # espera a API sair do ar antes de medir a volta
  for _ in $(seq 1 40); do
    [ "$(curl -s -o /dev/null -m 1 -w '%{http_code}' "$URL")" != "200" ] && break
    sleep 0.25
  done
  seg=$(esperar_200 "$t0")
  n_depois=$(docker inspect -f '{{.RestartCount}}' "$ID")
  log "[$modo] voltou a responder 200 em ${seg} s; reinícios: $n_antes -> $n_depois; estado: $(docker inspect -f '{{.State.Status}}' "$ID")"
  t1=$(date +%s.%N)
  for _ in $(seq 1 90); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$ID")" = "healthy" ] && break
    sleep 2
  done
  log "[$modo] healthcheck do Docker: $(docker inspect -f '{{.State.Health.Status}}' "$ID") (esperou $(echo "$(date +%s.%N) - $t1" | bc) s depois do 200)"
done

# Parada manual (docker stop) NÃO deve reiniciar: comportamento esperado de unless-stopped.
docker stop "$ID" >/dev/null
sleep 10
log "[docker stop] estado 10 s depois: $(docker inspect -f '{{.State.Status}}' "$ID") (esperado: exited)"
docker start "$ID" >/dev/null
esperar_200 "$(date +%s.%N)" | sed 's/^/[docker start] voltou em /; s/$/ s/' | tee -a "$SAIDA"
