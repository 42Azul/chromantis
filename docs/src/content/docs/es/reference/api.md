---
title: API local
description: Rutas para autenticar, buscar, revisar álbumes y etiquetar fotos.
---

El navegador, el bot y el cliente Android comparten el servicio de aplicación. Usa esta API HTTP desde un cliente local de confianza.

Rutas de solo lectura:

- `GET /api/v1/health`
- `GET /api/v1/stats`
- `GET /api/v1/years?from=2019&to=2021`
- `GET /api/v1/folders?q=city&limit=10`
- `GET /api/v1/images?q=city&limit=10`
- `GET /api/v1/album-images?path=<indexed-album-path>&limit=30&offset=0`
- `GET /api/v1/random?q=city&count=3`
- `GET /api/v1/people`

Usa `Authorization: Bearer <token>` o `X-API-Token: <token>`. Si hay un token configurado, la API exige autenticación salvo para `/api/v1/health`. `API_TOKEN` permite búsquedas en modo lectura. Los tokens por chat respetan el rol actual de Telegram y dejan de funcionar si el chat pierde el acceso.

Las sesiones familiares pueden explorar el índice mediante `/api/v1/years`, `/api/v1/folders` y `/api/v1/album-images`. Esta última ruta recibe la ruta exacta del álbum, codificada para URL, y devuelve `{"items": [...], "next_offset": ...}` ordenado por ruta de archivo. El máximo es de 50 elementos por página. `next_offset` vale `null` en la última. La consulta solo lee SQLite. El cliente puede solicitar las miniaturas por separado.

Pon el ID del propietario en `TELEGRAM_ADMIN_CHAT_ALLOWLIST` y añade su token individual a `API_CHAT_TOKENS`. Genera un token por chat con `python -c 'import secrets; print(secrets.token_urlsafe(32))'` y reinicia la API tras cambiar la configuración.

```dotenv
TELEGRAM_ADMIN_CHAT_ALLOWLIST=123456789
API_CHAT_TOKENS={"123456789":"replace-with-generated-token"}
```

| Método y ruta | Entrada JSON | Respuesta correcta | Acceso |
| --- | --- | --- | --- |
| `GET /api/v1/auth/me` | | `{"item": principal}` | Token de chat autorizado |
| `GET /api/v1/admin/chats` | | `{"items": [principal]}` | Administrador o propietario |
| `PATCH /api/v1/admin/chats/{chat_id}` | `{"role":"viewer"}` | `{"item": principal}` | Propietario, para chats dinámicos |
| `DELETE /api/v1/admin/chats/{chat_id}` | | `{"revoked":true}` | Administrador para lectores, propietario para todos los chats dinámicos |
| `GET /api/v1/admin/invites` | | `{"items": [invite]}` | Administrador para invitaciones activas de lector, propietario para todas |
| `POST /api/v1/admin/invites` | `{"role":"viewer","ttl_days":7}` | `201 {"item": invite}` | Administrador para lectores, propietario para administradores |
| `DELETE /api/v1/admin/invites/{code}` | | `{"item": invite}` | Administrador para lectores, propietario para administradores |

La identidad incluye `chat_id`, `role`, `username`, `first_name` y `auth_mode` (`static_owner`, `static_viewer` o `dynamic`). Una invitación incluye `code`, `role`, `created_by_chat_id`, `max_uses`, `used_count`, `expires_at`, `revoked_at` y `created_at`. Es de un solo uso y caduca a los siete días por defecto. Se admiten de uno a 30 días. Los errores incluyen `error` y un `code` para errores de rol o estado. Los cambios de rol, las revocaciones y los cambios de invitación se registran con el ID del chat que los realiza.

## Búsqueda y navegación

| Método y ruta | Solicitud | Respuesta correcta |
| --- | --- | --- |
| `GET /api/v1/people/{id}` | ID numérico del directorio | `{"item": person}` |
| `POST /api/v1/interpret` | `{"text":"show me 3 beach photos from 2021"}` | `{"item":{"action":"images","query":"beach 2021","count":3,"needs_clarification":false}}` |
| `GET /api/v1/image` | `?path=<indexed-image-path>` codificado para URL | Bytes del original |
| `GET /api/v1/browse` | Token de chat | Lote de navegación activo |
| `POST /api/v1/browse` | Token de chat y `{"action":"search","q":"beach 2021","count":3}` | Lote actualizado |
| `GET /api/v1/searches` | Token de chat con `pinned=true`, `limit` y `offset` opcionales | `{"items": [search]}` |
| `PATCH /api/v1/searches/{id}` | Token de chat y `{"pinned":true}` | `{"item": search}` |

Una persona contiene `id`, `display_name`, `aliases` y `folder_paths`. Un lote incluye `items`, `scope`, `q`, `count`, `folders`, `years` y `can_go_back`. Cada imagen incluye su ruta indexada, título, año, carpeta y motivo de coincidencia. Las estadísticas incluyen un objeto `item` además de sus campos originales. Los listados devuelven un array `items`.

Acciones de navegación: `search`, `random`, `more`, `open_folder`, `open_year`, `same_folder`, `same_year`, `related` y `back`. `q` es opcional para `search` y `random`. `count` admite de 1 a 50. Si el lote abarca varias carpetas o años, indica `folder` o `year` para acotar `same_folder`, `same_year` o `related`. Si falta el contexto, se devuelve 409. `open_folder` con `folder` y `open_year` con `year` empiezan un lote nuevo. Si no quedan resultados, `items` queda vacío y se conserva el último lote disponible. Las sesiones persisten por chat en SQLite y son independientes de la navegación de Telegram. La API y Telegram comparten las búsquedas recientes y fijadas del mismo chat. Cada búsqueda contiene `id`, `kind`, `query`, `count`, `searched_at` y `pinned`.

Los administradores y propietarios pueden editar personas. Cada escritura correcta devuelve `{"item": person}` con la persona actualizada.

| Método y ruta | Datos |
| --- | --- |
| `POST /api/v1/admin/people` | `{"display_name":"Ana"}` |
| `PATCH /api/v1/admin/people/{id}` | `{"display_name":"Anita"}` |
| `POST /api/v1/admin/people/{id}/aliases` | `{"alias":"Anni"}` |
| `POST /api/v1/admin/people/{id}/folders` | `{"path":"2021/2021-08-15_city_trip"}` |
| `DELETE /api/v1/admin/people/{id}/folders` | `?path=<folder-path>` codificado para URL |

## Etiquetado manual por foto

| Método y ruta | Solicitud | Acceso |
| --- | --- | --- |
| `GET /api/v1/photo-tags` | Repite `path` codificado para URL para entre 1 y 50 fotos indexadas | Con permiso de etiquetado |
| `PATCH /api/v1/photo-tags` | Identidades de las fotos y cambios que se aplican a todas | Con permiso de etiquetado |
| `GET /api/v1/confirmed-images` | `person` (nombre o alias) o `person_id`, con `limit` y `offset` opcionales | Lectores y sesiones familiares activas |

Las rutas de etiquetado devuelven `{"items": [...]}` en el orden de la selección. Cada elemento tiene `path`, `identity`, entradas `people` con `person_id` y `origin`, y entradas `manual_tags` con `tag` y `origin`. Usa los IDs de `GET /api/v1/album-review/people`, la ruta de cada foto de la galería y su `identity` en la respuesta de etiquetado.

```json
{
  "photos": [
    {"path": "2024/2024-03-16_picnic/synthetic.jpg", "identity": "0123456789abcdef0123456789abcdef"}
  ],
  "add_people": [7],
  "remove_people": [],
  "manual_add": ["family"],
  "manual_remove": []
}
```

Los cambios se aplican a toda la selección de forma atómica y se pueden reintentar. Si el cuerpo supera 16 KiB, la API devuelve 413. Divide las selecciones largas en solicitudes más pequeñas, cada una atómica. Una foto ausente o cambiada produce 409 para que el cliente recargue la selección. Las etiquetas tienen una palabra de hasta 40 letras. El registro de auditoría conserva el origen manual y el chat o la sesión familiar que hizo cada cambio. Los lectores pueden buscar. Consultar o guardar la selección de etiquetado requiere el permiso correspondiente. Las escrituras de sesiones familiares usan JSON y el mismo origen que la revisión de álbumes.

La búsqueda confirmada devuelve `{"items": [...], "next_offset": ...}` para vínculos explícitos a fotos. Por defecto muestra 30 elementos y admite hasta 50. Si la persona no está en el directorio, devuelve una lista vacía. `/api/v1/folders` y `/api/v1/images` conservan las coincidencias por álbum y por texto. Las etiquetas manuales por foto solo coinciden con las fotos editadas en `/api/v1/images`.

Una foto conserva su identidad y sus decisiones si no cambian su ruta, raíz, tamaño ni fecha de modificación. Si el listado omite tamaño o fecha, el índice retiene el último valor conocido. Eliminar la foto, cambiar la raíz o detectar un valor comparable distinto borra las decisiones activas. Un reemplazo con los mismos metadatos observados conserva la identidad. El etiquetado y la búsqueda leen SQLite, y el escaneo no abre los originales para esta función.

Ejecuta las pruebas sintéticas con `python -m unittest tests.test_photo_tags -v`.

## Revisión, enlaces y mantenimiento

| Método y ruta | Propósito |
| --- | --- |
| `GET /api/v1/album-review` | Siguiente álbum pendiente tras el ID `after`, o álbum de la ruta `path` |
| `GET /api/v1/album-review/people` | Directorio de personas y alias para etiquetar |
| `GET /api/v1/album-review/photos` | Hasta tres fotos indexadas para una ruta de álbum exacta |
| `POST /api/v1/album-review` | Guarda cambios con la revisión actual del álbum |
| `GET/POST /api/v1/album-review/batch` | Revisa sugerencias repetidas y guarda hasta 50 decisiones de forma atómica |
| `GET/POST /api/v1/album-shares` | Lista o crea permisos como propietario |
| `DELETE /api/v1/album-shares/{id}` | Revoca un permiso como propietario |
| `GET /api/v1/shared/{secret}` | Abre el álbum concedido. Sus rutas `/image` y `/thumbnail` se limitan a ese álbum. |
| `GET /api/v1/sync/runs?limit=10` | Escaneos recientes y recuentos |
| `GET /api/v1/archive-status` | Último índice correcto y estado de miniaturas |
| `GET /api/v1/image-dates?path=<indexed-image-path>` | Fechas de álbum, cámara y archivo por separado |

`GET /api/v1/folders` admite `sort=timeline`, `place`, `date_from` y `date_to`, además de `q`, `offset` y `limit`. El intervalo incluye ambas fechas. `POST /api/v1/refine` acepta `{"q":"playa","text":"antes de 2020"}` y devuelve una consulta acotada u opciones si hay ambigüedad.

Las colecciones de propietario usan `GET/POST /api/v1/collections`, `GET/DELETE /api/v1/collections/{id}`, `POST /api/v1/collections/{id}/entries` y `DELETE /api/v1/collections/{id}/entries/{entry-id}`. Para crear usa `name` y opcionalmente `entry`. Una entrada indica su `kind` (`folder` o `image`) y su `path` exacta.
