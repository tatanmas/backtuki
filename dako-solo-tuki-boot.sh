#!/bin/bash
# En Dako: desactiva auto-arranque de contenedores que NO son Tuki.
# Así en el próximo boot solo arrancarán los del stack Tuki (tuki-db, tuki-frontend, tuki-cloudflared, etc.).
# Immich, Mailu y otros no se levantarán solos.
# Ejecutar en Dako cuando Docker responda: ./backtuki/dako-solo-tuki-boot.sh

set -e
echo "Contenedores que conservan auto-arranque (tuki-*):"
docker ps -a --format '{{.Names}}' | grep -E '^tuki-' || true
echo ""
echo "Desactivando auto-arranque del resto (Immich, Mailu, etc.):"
count=0
for id in $(docker ps -aq); do
  name=$(docker inspect --format '{{.Name}}' "$id" 2>/dev/null | sed 's/^\///')
  if [[ -n "$name" && ! "$name" =~ ^tuki- ]]; then
    echo "  --restart=no: $name"
    docker update --restart=no "$id" 2>/dev/null || true
    count=$((count + 1))
  fi
done
echo ""
echo "Listo. $count contenedor(es) no-Tuki ya no arrancarán solos. Solo la plataforma Tuki se levantará al reiniciar."
