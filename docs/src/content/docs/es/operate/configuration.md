---
title: Configuración
description: Configura la fuente, SQLite, la API, los clientes opcionales y el enriquecimiento.
---

Empieza con el [archivo de configuración de ejemplo](https://github.com/42Azul/chromantis/blob/main/.env.example). Mantén privado tu `.env` local. Las variables de entorno tienen prioridad sobre el archivo. Reinicia la API y el bot cuando cambies su configuración.

| Ajuste | Valores y propósito |
| --- | --- |
| `SOURCE_TYPE` | `local` o `ftp`. |
| `SOURCE_ROOT` | Directorio que contiene las carpetas por año. Usa una ruta local absoluta o relativa al repositorio, o una ruta absoluta de FTP. |
| `FTP_HOST`, `FTP_PORT`, `FTP_USER`, `FTP_PASSWORD` | Datos de conexión de solo lectura para una fuente FTP. |
| `SQLITE_PATH` | Ruta del índice, con permiso de escritura y fuera del archivo. |
| `API_BIND_HOST`, `API_PORT` | Por defecto, `127.0.0.1:8787`. |
| `API_TRUST_LOCAL_PROXY` | Por defecto, `false`. Actívalo solo si un proxy HTTPS en la misma máquina sobrescribe `X-Forwarded-Proto`. |
| `API_TOKEN`, `API_CHAT_TOKENS` | Token compartido de solo lectura y tokens por chat como objeto JSON. Son opcionales. |
| `API_CURATOR_CHAT_IDS` | IDs de lectores autorizados a etiquetar álbumes, separados por comas. |
| `TELEGRAM_TOKEN`, `TELEGRAM_ACCESS_CODE` | Token del bot y código fijo opcional para lectores. |
| `TELEGRAM_CHAT_ALLOWLIST`, `TELEGRAM_ADMIN_CHAT_ALLOWLIST` | IDs de lectores y propietarios estáticos, separados por comas. |
| `THUMBNAIL_CACHE_MIB` | Límite de la caché de miniaturas JPEG. El valor `0` (por defecto) la desactiva. |
| `QUERY_INTERPRETER_COMMAND`, `QUERY_INTERPRETER_TIMEOUT` | Comando opcional para un modelo local y tiempo límite en segundos (10 por defecto). |
| `ENRICHMENT_SEARCH` | Pon `true` para buscar en resultados de OCR, descripciones y etiquetas de objetos ya guardados. Por defecto, `false`. |
| `LOG_LEVEL` | Por defecto, `INFO`. Usa `DEBUG` para más detalles sobre escaneos y consultas. |

Consulta [Acceso privado](../start/private-access.md) para configurar permisos y sesiones familiares, y [Pruebas de búsqueda local](../reference/experiments.md) para configurar modelos.

## No aparecen las miniaturas

El instalador rápido del NAS instala el extra de Telegram. No instala el generador opcional de imágenes ni activa las miniaturas. Comprueba primero `GET /api/v1/archive-status` con un cliente autorizado: `item.thumbnails` debe ser `true`. Ver una carpeta sin portada no demuestra por sí solo un fallo del cliente.

Para activarlas de forma explícita en el NAS, instala `'.[thumbnails]'` en el mismo entorno Python que ejecuta la API, pon `THUMBNAIL_CACHE_MIB=64` en su `.env` privado y reinicia la API. Mantén `SQLITE_PATH` fuera del archivo de solo lectura: la caché se crea junto a SQLite. Las variables de entorno tienen prioridad sobre `.env`. Si el estado sigue siendo falso, revisa si el registro de la API indica que falta el generador o que la ubicación de la caché no es válida.

Con un cliente local autorizado, pide `/api/v1/thumbnail?path=<ruta-indexada>` para un JPEG pequeño ya indexado. `404` puede indicar miniaturas desactivadas, una ruta sin indexar o un archivo que ya no existe; `422`, una imagen no compatible, demasiado grande o un índice que no corresponde a la fuente; `502`, que no se ha podido acceder al archivo. Prueba una segunda foto si solo falla una. No incluyas credenciales, rutas ni imágenes en informes compartidos. La comprobación solo lee la foto elegida; no inicia una indexación.

Android y la galería web reutilizan miniaturas en una caché de memoria de hasta 4 MiB por sesión del cliente. Las listas incluyen una `identity` opaca; al reindexar una foto sustituida cambia y se descarta la miniatura anterior. Los servidores antiguos que no la envían siguen funcionando, con una petición nueva en lugar de reutilizar la imagen. Cerrar sesión, volver a entrar o recibir una respuesta no autorizada vacía la caché. En el navegador también se limita a 64 entradas y no se guarda en almacenamiento persistente. Al volver a abrir una galería se consulta su lista protegida; una sesión revocada no puede reabrirla mediante miniaturas guardadas. La revocación no puede retirar píxeles ya mostrados ni fotos descargadas explícitamente.
