#!/usr/bin/env python3
# Ejecutar en Dako CON DOCKER PARADO (systemctl stop docker).
# Solo estos contenedores conservan restart; todo lo demás (Mailu, Immich, etc.) pasa a restart=no.

import json
import os

# Solo la plataforma Tuki puede auto-arrancar. Cualquier otro nombre → restart=no
TUKI_NAMES = {
    "/tuki-db", "/tuki-redis", "/tuki-backend-a", "/tuki-backend-b",
    "/tuki-celery-worker", "/tuki-celery-beat", "/tuki-frontend",
    "/tuki-cloudflared", "/tuki-whatsapp-service",
}

base = "/var/lib/docker/containers"
if not os.path.isdir(base):
    print("No existe", base, "(¿Docker instalado? ¿Ejecutando como root?)")
    exit(1)

for cid in os.listdir(base):
    p = os.path.join(base, cid)
    config_path = os.path.join(p, "config.v2.json")
    host_path = os.path.join(p, "hostconfig.json")
    if not os.path.isfile(config_path) or not os.path.isfile(host_path):
        continue
    try:
        with open(config_path) as f:
            config = json.load(f)
        name = config.get("Name", "")
        if name in TUKI_NAMES:
            continue
        with open(host_path) as f:
            host = json.load(f)
        if host.get("RestartPolicy", {}).get("Name") == "no":
            continue
        host["RestartPolicy"] = host.get("RestartPolicy") or {}
        host["RestartPolicy"]["Name"] = "no"
        with open(host_path, "w") as f:
            json.dump(host, f, indent=2)
        print("restart=no:", name)
    except Exception as e:
        print("Error", cid, e)

print("Listo. Ahora puedes: sudo systemctl start docker && sudo systemctl enable docker")
