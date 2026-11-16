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
| `API_TOKEN`, `API_CHAT_TOKENS` | Token compartido de solo lectura y tokens por chat como objeto JSON. Son opcionales. |
| `API_CURATOR_CHAT_IDS` | IDs de lectores autorizados a etiquetar álbumes, separados por comas. |
| `TELEGRAM_TOKEN`, `TELEGRAM_ACCESS_CODE` | Token del bot y código fijo opcional para lectores. |
| `TELEGRAM_CHAT_ALLOWLIST`, `TELEGRAM_ADMIN_CHAT_ALLOWLIST` | IDs de lectores y propietarios estáticos, separados por comas. |
| `THUMBNAIL_CACHE_MIB` | Límite de la caché de miniaturas JPEG. El valor `0` (por defecto) la desactiva. |
| `QUERY_INTERPRETER_COMMAND`, `QUERY_INTERPRETER_TIMEOUT` | Comando opcional para un modelo local y tiempo límite en segundos (10 por defecto). |
| `ENRICHMENT_SEARCH` | Pon `true` para buscar en resultados de OCR, descripciones y etiquetas de objetos ya guardados. Por defecto, `false`. |
| `LOG_LEVEL` | Por defecto, `INFO`. Usa `DEBUG` para más detalles sobre escaneos y consultas. |

Consulta [Acceso privado](../start/private-access.md) para configurar permisos y sesiones familiares, y [Pruebas de búsqueda local](../reference/experiments.md) para configurar modelos.
