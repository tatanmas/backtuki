# 🔧 Troubleshooting - Autenticación GCP sin Navegador

Esta guía te ayuda a resolver problemas comunes al configurar la autenticación de Google Cloud Platform en tu servidor remoto sin interfaz gráfica.

---

## 📋 Tabla de Contenidos

1. [Problemas Comunes](#problemas-comunes)
2. [Verificar Permisos del Usuario](#verificar-permisos-del-usuario)
3. [Problemas con Service Account](#problemas-con-service-account)
4. [Problemas de Acceso a Recursos](#problemas-de-acceso-a-recursos)
5. [Revocar y Recrear Service Account](#revocar-y-recrear-service-account)
6. [Rotar Claves](#rotar-claves)
7. [Logs y Depuración](#logs-y-depuración)

---

## 🔍 Problemas Comunes

### Error: "Token expirado" o "Reauthentication failed"

**Síntoma:**
```
ERROR: (gcloud.projects.list) There was a problem refreshing your current auth tokens: 
Reauthentication failed. cannot prompt during non-interactive execution.
```

**Causa:** El token de autenticación del usuario en tu Mac expiró.

**Solución:**
1. En tu Mac, ejecuta:
   ```bash
   gcloud auth login
   ```
2. Esto abrirá tu navegador. Inicia sesión con `tecnologia@tuki.cl`
3. Vuelve a ejecutar el script:
   ```bash
   ./paso2-service-account.sh
   ```

---

### Error: "Permission denied" al crear Service Account

**Síntoma:**
```
ERROR: (gcloud.iam.service-accounts.create) Permission denied.
```

**Causa:** Tu usuario no tiene permisos para crear Service Accounts.

**Solución:**
1. Verifica tus permisos:
   ```bash
   gcloud projects get-iam-policy tukiprod \
     --flatten="bindings[].members" \
     --filter="bindings.members:user:$(gcloud config get-value account)" \
     --format="value(bindings.role)"
   ```
2. Debes tener uno de estos roles:
   - `roles/owner`
   - `roles/iam.serviceAccountAdmin`
   - `roles/editor` (permite crear Service Accounts)

3. Si no tienes permisos, contacta al administrador del proyecto para que te asigne el rol necesario.

---

### Error: "Service Account already exists"

**Síntoma:**
```
ERROR: (gcloud.iam.service-accounts.create) Resource already exists.
```

**Causa:** El Service Account ya existe en GCP.

**Solución:**
El script te dará opciones:
- **`use`** - Usar el Service Account existente (recomendado si está correctamente configurado)
- **`recreate`** - Eliminar y crear uno nuevo (si necesitas empezar desde cero)
- **`update`** - Mantener el existente y solo actualizar permisos

Si eliges `use`, el script verificará que tenga los permisos necesarios.

---

### Error: "Cannot connect via SSH"

**Síntoma:**
```
Connection timeout
Permission denied (publickey,password)
```

**Causa:** Problema con la conexión SSH al servidor.

**Solución:**
1. Verifica que el servidor esté accesible:
   ```bash
   ssh -p 2222 tatan@tukitickets.duckdns.org
   ```
2. Verifica que `expect` esté instalado en tu Mac:
   ```bash
   which expect
   ```
   Si no está instalado:
   ```bash
   brew install expect
   ```
3. Verifica que la contraseña sea correcta en el script.

---

### Error: "gcloud not found" en el servidor

**Síntoma:**
```
command not found: gcloud
```

**Causa:** gcloud CLI no está instalado en el servidor.

**Solución:**
1. Ejecuta primero el script de instalación:
   ```bash
   ./paso1-instalar-gcloud.sh
   ```
2. O instálalo manualmente en el servidor:
   ```bash
   ssh -p 2222 tatan@tukitickets.duckdns.org
   curl https://sdk.cloud.google.com | bash
   exec -l $SHELL
   export PATH=$PATH:$HOME/google-cloud-sdk/bin
   ```

---

### Error: "Access denied" al acceder a Cloud SQL

**Síntoma:**
```
ERROR: (gcloud.sql.instances.describe) User does not have permission to access instance
```

**Causa:** El Service Account no tiene el rol necesario para acceder a Cloud SQL.

**Solución:**
1. Verifica los roles del Service Account:
   ```bash
   gcloud projects get-iam-policy tukiprod \
     --flatten="bindings[].members" \
     --filter="bindings.members:serviceAccount:tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com" \
     --format="value(bindings.role)"
   ```
2. Debe tener el rol `roles/cloudsql.client`
3. Si no lo tiene, asígnalo:
   ```bash
   gcloud projects add-iam-policy-binding tukiprod \
     --member="serviceAccount:tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com" \
     --role="roles/cloudsql.client"
   ```

---

### Error: "Access denied" al acceder a Cloud Storage

**Síntoma:**
```
AccessDeniedException: 403 Access denied to bucket
```

**Causa:** El Service Account no tiene permisos para acceder a Cloud Storage.

**Solución:**
1. Verifica los roles del Service Account (ver comando arriba)
2. Debe tener uno de estos roles:
   - `roles/storage.objectViewer` (para leer)
   - `roles/storage.objectCreator` (para escribir)
3. Si no los tiene, asígnalos:
   ```bash
   gcloud projects add-iam-policy-binding tukiprod \
     --member="serviceAccount:tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com" \
     --role="roles/storage.objectViewer"
   
   gcloud projects add-iam-policy-binding tukiprod \
     --member="serviceAccount:tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com" \
     --role="roles/storage.objectCreator"
   ```

---

### Error: "Key file not found" o "Permission denied" en el servidor

**Síntoma:**
```
ERROR: (gcloud.auth.activate-service-account) Could not read key file
```

**Causa:** El archivo JSON no existe o tiene permisos incorrectos.

**Solución:**
1. Verifica que el archivo existe en el servidor:
   ```bash
   ssh -p 2222 tatan@tukitickets.duckdns.org
   ls -l ~/gcp-key.json
   ```
2. Si no existe, vuelve a ejecutar `./paso2-service-account.sh`
3. Si existe pero tiene permisos incorrectos, corrígelos:
   ```bash
   chmod 600 ~/gcp-key.json
   ```

---

## 🔐 Verificar Permisos del Usuario

### Verificar roles del usuario en Mac

```bash
# Ver todos tus roles en el proyecto
gcloud projects get-iam-policy tukiprod \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:$(gcloud config get-value account)" \
  --format="table(bindings.role)"
```

### Roles necesarios para crear Service Accounts

- **Mínimo requerido:** `roles/iam.serviceAccountAdmin`
- **Recomendado:** `roles/owner` (tiene todos los permisos)
- **Alternativa:** `roles/editor` (permite crear Service Accounts)

---

## 🏗️ Problemas con Service Account

### Verificar Service Account existe

```bash
gcloud iam service-accounts describe \
  tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com \
  --project=tukiprod
```

### Listar todos los Service Accounts del proyecto

```bash
gcloud iam service-accounts list --project=tukiprod
```

### Verificar roles del Service Account

```bash
gcloud projects get-iam-policy tukiprod \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

### Roles necesarios del Service Account

- `roles/cloudsql.client` - Acceso a Cloud SQL
- `roles/storage.objectViewer` - Leer desde Cloud Storage
- `roles/storage.objectCreator` - Escribir backups en Cloud Storage

---

## 🔓 Problemas de Acceso a Recursos

### Verificar acceso a Cloud SQL desde el servidor

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
export PATH=$PATH:$HOME/google-cloud-sdk/bin
gcloud sql instances describe tuki-db-prod --project=tukiprod
```

**Si falla:**
1. Verifica que el Service Account tenga `roles/cloudsql.client`
2. Verifica que la instancia Cloud SQL exista
3. Verifica que el proyecto sea correcto

### Verificar acceso a Cloud Storage desde el servidor

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
export PATH=$PATH:$HOME/google-cloud-sdk/bin
gsutil ls gs://tuki-media-prod-1759240560/
```

**Si falla:**
1. Verifica que el Service Account tenga `roles/storage.objectViewer`
2. Verifica que el bucket exista
3. Verifica que el nombre del bucket sea correcto

### Verificar autenticación activa en el servidor

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
export PATH=$PATH:$HOME/google-cloud-sdk/bin
gcloud auth list
```

Debe mostrar una cuenta Service Account con estado `ACTIVE`.

---

## 🔄 Revocar y Recrear Service Account

### Si necesitas empezar desde cero

1. **Eliminar Service Account:**
   ```bash
   gcloud iam service-accounts delete \
     tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com \
     --project=tukiprod \
     --quiet
   ```

2. **Eliminar clave JSON en el servidor:**
   ```bash
   ssh -p 2222 tatan@tukitickets.duckdns.org
   rm -f ~/gcp-key.json
   ```

3. **Eliminar clave JSON local:**
   ```bash
   rm -f ./gcp-key-tuki-homeserver-migrator.json
   ```

4. **Ejecutar script nuevamente:**
   ```bash
   ./paso2-service-account.sh
   ```

---

## 🔐 Rotar Claves

### Por qué rotar claves

Por seguridad, se recomienda rotar las claves del Service Account cada 90 días.

### Cómo rotar claves

1. **Crear nueva clave:**
   ```bash
   gcloud iam service-accounts keys create \
     ./gcp-key-tuki-homeserver-migrator-NEW.json \
     --iam-account=tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com \
     --project=tukiprod
   ```

2. **Transferir nueva clave al servidor:**
   ```bash
   scp -P 2222 ./gcp-key-tuki-homeserver-migrator-NEW.json \
     tatan@tukitickets.duckdns.org:~/gcp-key.json
   ```

3. **Configurar nueva clave en el servidor:**
   ```bash
   ssh -p 2222 tatan@tukitickets.duckdns.org
   export PATH=$PATH:$HOME/google-cloud-sdk/bin
   chmod 600 ~/gcp-key.json
   gcloud auth activate-service-account \
     --key-file=~/gcp-key.json
   ```

4. **Verificar que funciona:**
   ```bash
   gcloud auth list
   gcloud sql instances describe tuki-db-prod --project=tukiprod
   ```

5. **Eliminar clave antigua:**
   ```bash
   # Listar todas las claves
   gcloud iam service-accounts keys list \
     --iam-account=tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com \
     --project=tukiprod
   
   # Eliminar clave antigua (reemplaza KEY_ID)
   gcloud iam service-accounts keys delete KEY_ID \
     --iam-account=tuki-homeserver-migrator@tukiprod.iam.gserviceaccount.com \
     --project=tukiprod \
     --quiet
   ```

---

## 📊 Logs y Depuración

### Ejecutar script con modo verbose

```bash
bash -x ./paso2-service-account.sh
```

### Verificar logs en el servidor

```bash
ssh -p 2222 tatan@tukitickets.duckdns.org
# Ver configuración de gcloud
gcloud config list
gcloud auth list

# Verificar PATH
echo $PATH
which gcloud

# Verificar archivo JSON
ls -l ~/gcp-key.json
```

### Verificar desde Mac

```bash
# Ver autenticación
gcloud auth list

# Ver proyecto
gcloud config get-value project

# Ver Service Accounts
gcloud iam service-accounts list --project=tukiprod

# Ver políticas IAM
gcloud projects get-iam-policy tukiprod
```

### Ejecutar script de verificación

```bash
./verificar-autenticacion.sh
```

Este script verifica automáticamente:
- Conexión SSH
- gcloud instalado
- Autenticación activa
- Proyecto configurado
- Permisos de archivo JSON
- Acceso a Cloud SQL
- Acceso a Cloud Storage
- Roles del Service Account

---

## ⚠️ Seguridad

### Buenas prácticas

1. **Permisos de archivo:** Siempre `chmod 600` para archivos JSON
2. **No subir a Git:** Verifica que `.gitignore` incluya `*.json` y `gcp-key-*.json`
3. **Principio de menor privilegio:** Asigna solo los roles necesarios
4. **Rotación periódica:** Rota claves cada 90 días
5. **Revocar claves antiguas:** Elimina claves que ya no uses
6. **Monitoreo:** Revisa logs de auditoría en GCP periódicamente

### Verificar que JSON no está en Git

```bash
git status
git ls-files | grep -i "gcp-key\|\.json"
```

Si aparece algún archivo JSON, elimínalo del repositorio:
```bash
git rm --cached path/to/file.json
```

---

## 📞 Obtener Ayuda

Si después de seguir esta guía aún tienes problemas:

1. Ejecuta el script de verificación: `./verificar-autenticacion.sh`
2. Revisa los logs en `logs/` (si existen)
3. Consulta la documentación oficial:
   - [gcloud auth](https://cloud.google.com/sdk/gcloud/reference/auth)
   - [Service Accounts](https://cloud.google.com/iam/docs/service-accounts)
   - [IAM Troubleshooting](https://cloud.google.com/iam/docs/troubleshooting)

---

**Última actualización:** 2025-01-27

