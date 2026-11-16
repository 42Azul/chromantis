---
title: Instalar Chromantis
description: Prueba el ejemplo, configura un NAS o conecta un archivo local o FTP.
---

Necesitas Python 3.10 o posterior, un archivo de fotos y una ubicación con permiso de escritura para el índice SQLite. Chromantis lee las fotos del archivo y guarda por separado los metadatos y las correcciones.

## Prueba con las carpetas de ejemplo

Con Git y Python instalados, clona el repositorio y arranca el servicio en tu ordenador:

```bash
git clone https://github.com/42Azul/chromantis.git
cd chromantis
export SOURCE_TYPE=local
export SOURCE_ROOT=tests/fixtures/ftp_tree/server_root/photos/archive
export SQLITE_PATH=./data/chromantis-demo.db
python3 scripts/reindex_source.py
python3 scripts/run_api.py
```

Abre [http://127.0.0.1:8787/](http://127.0.0.1:8787/) y busca `city 2021`. El ejemplo usa nombres de archivo para probar el índice. Usa tus propias fotos para probar las vistas previas. Pulsa Ctrl+C para detener la API. Este ejemplo sin autenticación se limita a la interfaz local.

## Configura un NAS con Telegram

1. Clona el repositorio en el NAS y entra en su directorio.
2. Ejecuta `bash scripts/setup_nas.sh`.
3. Indica el directorio que contiene las carpetas de cada año e introduce el token del bot cuando se te pida. El token queda oculto al escribirlo.
4. Abre el enlace de Telegram que aparece en la terminal para registrar tu chat como propietario. Envía `/start` y prueba `/years`.

El instalador crea un entorno virtual, escribe un `.env` privado con un token independiente para el navegador, indexa los cambios y arranca la API y el bot. En un NAS antiguo puede usar `uv` para instalar Python 3.12 en tu cuenta. Si ya sabes el ID de tu chat, define `CHROMANTIS_OWNER_CHAT_ID` antes de ejecutar el instalador.

| Para | Ejecuta desde el repositorio |
| --- | --- |
| Arrancar los servicios ya configurados | `bash scripts/setup_nas.sh --start-only` |
| Configurar, indexar y terminar | `bash scripts/setup_nas.sh --setup-only` |
| Sustituir el token del bot | `bash scripts/setup_nas.sh --rotate-token` |

Abre la web desde tu ordenador con un [túnel SSH](./private-access.md#abre-la-web-del-nas-desde-tu-ordenador).

## Configura el navegador manualmente

Usa esta opción para una instalación solo web, una fuente FTP o un entorno Python existente.

```bash
git clone https://github.com/42Azul/chromantis.git
cd chromantis
python3 -m venv .venv
cp .env.example .env
chmod 600 .env
```

Configura la fuente y la base de datos en `.env`. Para un archivo local:

```dotenv
SOURCE_TYPE=local
SOURCE_ROOT=/mnt/photos
SQLITE_PATH=./data/chromantis.db
```

Para FTP, usa `SOURCE_TYPE=ftp`, una ruta FTP absoluta en `SOURCE_ROOT` y las opciones `FTP_HOST`, `FTP_PORT`, `FTP_USER` y `FTP_PASSWORD`. Emplea una cuenta de solo lectura. El escáner espera una estructura de `año/álbum/foto` bajo la raíz y omite directorios más profundos.

Mantén `API_BIND_HOST=127.0.0.1`. Genera un token con `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` y guárdalo en `API_TOKEN` para acceder en modo lectura desde el navegador. Para administrar el archivo, [configura un token de propietario](./private-access.md#configura-un-token-de-propietario).

```bash
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/reindex_source.py --progress-every 500
.venv/bin/python scripts/run_api.py
```

Abre el navegador y comprueba que aparecen los años. Si también quieres usar Telegram, instala `'.[telegram]'` con `.venv/bin/python -m pip install`, rellena `TELEGRAM_TOKEN` y ejecuta `.venv/bin/python scripts/run_bot.py` en otra terminal.

## Si algo falla al empezar

| Síntoma | Qué comprobar |
| --- | --- |
| No se indexa ninguna foto | Usa como raíz el directorio que contiene los años. Prueba `--verbose --show-skipped` con un archivo pequeño. |
| No abre la web | Ábrela en el equipo que ejecuta la API o reenvía el puerto local mediante SSH. |
| Falla el acceso | Comprueba el token o genera otro código familiar. Reinicia la API después de editar `.env`. |
| No carga una foto | Comprueba que el disco está montado o que FTP responde. Las listas y la revisión de álbumes siguen disponibles desde SQLite. |
