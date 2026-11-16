#!/usr/bin/env bash
# Mede em quanto tempo a API volta a responder depois de o contêiner morrer.
# Uso: medir_reinicio.sh <saida.txt>   (compose já no ar; só para o CI)
set -u
SAIDA="${1:-reinicio.txt}"
URL="http://localhost:7071/api/health"
COMPOSE="docker compose -f infra/docker-compose.yml"
: > "$SAIDA"
log() { echo "$*" | tee -a "$SAIDA"; }
agora() { date +%s.%N; }
dif() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.1f", b-a}'; }
http() { curl -s -o /dev/null -m 2 -w '%{http_code}' "$URL" || true; }

# Segundos até /api/health responder 200 (teto de 120 s; devolve TIMEOUT).
esperar_200() {
  local t0=$1
  while true; do
    [ "$(http)" = "200" ] && { dif "$t0" "$(agora)"; return 0; }
    [ "$(dif "$t0" "$(agora)" | cut -d. -f1)" -ge 120 ] && { echo "TIMEOUT"; return 1; }
    sleep 0.5
  done
}

esperar_saida_do_ar() {
  for _ in $(seq 1 40); do [ "$(http)" != "200" ] && return 0; sleep 0.25; done
}

ID=$($COMPOSE ps -q api)
estado() { docker inspect -f '{{.State.Status}}' "$ID"; }
saude() { docker inspect -f '{{.State.Health.Status}}' "$ID"; }
reinicios() { docker inspect -f '{{.RestartCount}}' "$ID"; }
log "política de reinício: $(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$ID")"
log "saúde antes: $(saude)"

# 1) Queda do processo (SIGKILL no PID 1 do contêiner, pelo host): é o que o OOM killer faz.
PID=$(docker inspect -f '{{.State.Pid}}' "$ID")
n0=$(reinicios); t0=$(agora)
sudo kill -9 "$PID"
esperar_saida_do_ar
seg=$(esperar_200 "$t0")
log "[queda do processo, SIGKILL] voltou a responder 200 em ${seg} s; reinícios: $n0 -> $(reinicios); estado: $(estado)"
t1=$(agora)
for _ in $(seq 1 60); do [ "$(saude)" = "healthy" ] && break; sleep 2; done
log "[queda do processo, SIGKILL] healthcheck do Docker: $(saude) ($(dif "$t1" "$(agora)") s depois do 200)"

# 2) docker kill: o Docker trata como parada pedida pelo operador e NÃO reinicia (registrado como observado).
n0=$(reinicios); t0=$(agora)
docker kill "$ID" >/dev/null
sleep 30
log "[docker kill] estado 30 s depois: $(estado); reinícios: $n0 -> $(reinicios)"
docker start "$ID" >/dev/null
seg=$(esperar_200 "$t0")
log "[docker kill + docker start manual] voltou a responder 200 em ${seg} s (inclui os 30 s de observação)"

# 3) docker stop também não reinicia (esperado em unless-stopped).
docker stop "$ID" >/dev/null
sleep 10
log "[docker stop] estado 10 s depois: $(estado) (esperado: exited)"
docker start "$ID" >/dev/null
seg=$(esperar_200 "$(agora)")
log "[docker start depois do stop] voltou a responder 200 em ${seg} s"
