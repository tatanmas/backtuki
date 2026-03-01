#!/bin/bash
#
# Obtener logs de producción (Dako) vía SSH.
# Descubre contenedores Tuki en vivo (backend-a/b, whatsapp, celery, frontend) y muestra logs de cada uno.
#
# Uso desde la raíz del repo:
#   ./backtuki/logs-dako.sh dako              → imprime logs (200 líneas por contenedor)
#   ./backtuki/logs-dako.sh dako --tail 500   → últimas 500 líneas por contenedor
#   ./backtuki/logs-dako.sh dako --save       → guarda en logs-dako-YYYYMMDD-HHMM.txt
#
# Sin "dako": usa DAKO_HOST, DAKO_PORT, DAKO_USER (tatan@tukitickets.duckdns.org -p 2222).
# Alias recomendado: dako-logs → scripts/dako-logs.sh (que invoca este script con dako).
#

set -e

SAVE=""
TAIL_LINES="${TAIL_LINES:-200}"
[ "$1" = "--save" ] && { SAVE=1; shift; }
[ "$2" = "--save" ] && SAVE=1
[ "$1" = "--tail" ] && [ -n "${2:-}" ] && { TAIL_LINES="$2"; shift 2; }

if [ "$1" = "dako" ]; then
  SSH_TARGET="dako"
  SSH_OPTS="-o ConnectTimeout=10 -o BatchMode=yes"
  SSH_DESC="dako (alias ~/.ssh/config)"
else
  DAKO_HOST="${DAKO_HOST:-tukitickets.duckdns.org}"
  DAKO_PORT="${DAKO_PORT:-2222}"
  DAKO_USER="${DAKO_USER:-tatan}"
  SSH_TARGET="$DAKO_USER@$DAKO_HOST"
  SSH_OPTS="-p $DAKO_PORT -o ConnectTimeout=10 -o BatchMode=yes"
  SSH_DESC="$DAKO_USER@$DAKO_HOST -p $DAKO_PORT"
fi

echo "══════════════════════════════════════════════════════════════"
echo "  LOGS PRODUCCIÓN DAKO  →  $SSH_DESC"
echo "══════════════════════════════════════════════════════════════"
echo ""

run_remote() {
  ssh $SSH_OPTS "$SSH_TARGET" bash -s
}

# Contenedores Tuki de los que queremos logs (sin mail/immich). Se descubren en vivo.
TUKI_LOG_PATTERN='^tuki-(backend|whatsapp-service|celery-worker|celery-beat|frontend)'

output_logs() {
  run_remote << REMOTE
set -e
TAIL_LINES='$TAIL_LINES'
echo "─── Contenedores Tuki activos (backend, whatsapp, celery, frontend) ───"
containers=\$(docker ps --format '{{.Names}}' 2>/dev/null | grep -E '$TUKI_LOG_PATTERN' || true)
if [ -z "\$containers" ]; then
  echo "(ningún contenedor encontrado con patrón tuki-backend*, whatsapp, celery, frontend)"
  echo "Todos los que tienen 'tuki-' en el nombre:"
  docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "tuki-|NAMES" || true
  exit 0
fi
echo "\$containers" | while read -r c; do echo "  - \$c"; done
echo ""

for c in \$containers; do
  echo "─── \$c (últimas \${TAIL_LINES} líneas) ───"
  docker logs "\$c" --tail "\$TAIL_LINES" 2>&1
  echo ""
done

echo "─── Resumen ERROR/Exception (backend + whatsapp, últimas 500) ───"
for c in \$containers; do
  case "\$c" in
    *backend*|*whatsapp*)
      docker logs "\$c" --tail 500 2>&1 | grep -E "ERROR|Exception|Traceback|timeout|Read timed out|500|whatsapp" || true
      ;;
  esac
done
echo "─── Fin ───"
REMOTE
}

if [ "$SAVE" = "1" ]; then
  FNAME="logs-dako-$(date +%Y%m%d-%H%M).txt"
  # Si se ejecuta desde backtuki/, guardar en repo root
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  output_logs | tee "$ROOT/$FNAME"
  echo ""
  echo "Guardado en $ROOT/$FNAME"
else
  output_logs
fi
