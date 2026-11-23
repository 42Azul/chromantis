---
title: Índice, miniaturas y copias de seguridad
description: Actualiza el catálogo, limita el coste de las miniaturas y recupera SQLite.
---

## Incorpora las carpetas nuevas

En la web, entra con un token de propietario y abre **Admin → Recent indexing runs**. Pulsa **Find new folders** para iniciar un escaneo incremental y **Refresh status** para consultar su número, resultado y recuentos. El escaneo usa el archivo configurado y se ejecuta en segundo plano. Solo el propietario puede iniciarlo.

Después de añadir fotos al archivo, ejecuta desde el repositorio:

```bash
.venv/bin/python scripts/reindex_source.py --incremental --progress-every 500
```

El modo incremental lista el subárbol configurado, aplica los cambios y retira entradas ausentes solo si pudo completar el listado. La API y la línea de comandos comparten un archivo de bloqueo junto al índice SQLite local para los escaneos completos e incrementales. Si hay un escaneo en curso, la siguiente solicitud termina sin iniciar otro. Conserva el archivo de bloqueo. Tras un cierre inesperado, el siguiente escaneo marca la ejecución interrumpida como fallida. Ejecuta sin `--incremental` si cambias las reglas de interpretación y quieres actualizar los metadatos derivados.

El índice reconoce una fecha inicial con el formato `AAAAMMDD - Título` o un nombre que solo contenga `AAAAMMDD`, si la fecha es válida y su año coincide con el de la carpeta. Ejecuta un escaneo completo para actualizar las fechas derivadas en un índice existente. Se conservan las correcciones manuales y los originales se mantienen en solo lectura.

La web muestra la fecha del último índice correcto. `GET /api/v1/sync/runs?limit=10` incluye el inicio y el fin de cada ejecución, los recuentos y los errores. Para escanear cada día a las 03:20, en la zona horaria del NAS, adapta las rutas del repositorio y del registro en esta entrada de cron:

```text
20 3 * * * cd /path/to/chromantis && .venv/bin/python scripts/reindex_source.py --incremental >> /path/to/chromantis-sync.log 2>&1
```

## Carga miniaturas solo cuando hagan falta

Instala el extra opcional de Pillow en el entorno de la API:

```bash
.venv/bin/python -m pip install '.[thumbnails]'
```

Pon `THUMBNAIL_CACHE_MIB=64` en `.env` y reinicia la API. La caché se guarda junto a SQLite y admite hasta 2.048 miniaturas JPEG dentro del límite configurado. Genera imágenes de hasta 480 px bajo demanda y elimina primero las entradas más antiguas. La generación admite originales de hasta 32 MiB y 30 megapíxeles.

Puedes abrir las miniaturas guardadas con la fuente desconectada. Si el índice detecta que cambió el tamaño o la fecha de modificación de una foto, invalida su miniatura. Define el límite en `0` para desactivarlas.

## Lee la fecha de captura de la cámara

Con el mismo extra de Pillow, procesa un lote pequeño de JPEG indexados:

```bash
.venv/bin/python scripts/index_capture_dates.py --limit 25 --album "2024/2024-08-04_beach"
```

Omite `--album` para tomar el siguiente lote de todo el índice. El lector examina hasta 512 KiB por JPEG, guarda el día que indicó la cámara si es válido y omite los archivos sin cambios en las siguientes ejecuciones. No lee las coordenadas GPS ni decodifica los píxeles. Los errores de lectura se pueden reintentar.

## Haz una copia de SQLite

```bash
mkdir -p backups
.venv/bin/python scripts/database_backup.py create backups/chromantis.sqlite
.venv/bin/python scripts/database_backup.py verify backups/chromantis.sqlite
```

La copia en línea incluye los cambios confirmados del registro WAL y muestra el tamaño y el resumen SHA-256. Contiene datos privados del índice y del etiquetado, incluidos los registros de acceso. Guarda una copia privada fuera del NAS. Haz por separado las copias de las fotos originales y de la configuración local.

## Restaura en un archivo nuevo

```bash
.venv/bin/python scripts/database_backup.py \
  --database data/restored-chromantis.db restore backups/chromantis.sqlite
```

La restauración aplica las migraciones de esquema actuales y evita sobrescribir bases de datos existentes. Detén la API y el bot antes de cambiar `SQLITE_PATH`, conserva la base de datos anterior y reinicia con la restaurada. Comprueba un álbum que hayas corregido y una colección privada. Reindexa si cambió la ubicación o el contenido del archivo de fotos. Para hacer, verificar o restaurar la copia basta con SQLite.

## Falta una carpeta de un año

La vista por años agrupa los álbumes indexados bajo el año de cuatro cifras. Si el año está dividido en `2003(1)` y `2003(2)`, recorre todas las páginas y compara las rutas. Dos álbumes con el mismo título pueden tener rutas distintas. Los clientes muestran 30 álbumes por página.

Si la carpeta no aparece en ninguna página, revisa el último escaneo en **Estado del archivo**. En el NAS, compara el nombre exacto de la carpeta y la profundidad que ve el origen configurado con la estructura `año/álbum/foto.jpg`. Si usas FTP, comprueba si el escaneo empleó MLSD o recurrió a NLST y si el listado del origen incluye ambas carpetas. Para aparecer en la vista por años, un álbum necesita al menos una imagen indexada. Mantén las rutas y los registros de escaneo en el entorno local.
