---
title: Bot de Telegram
description: Busca en el chat, explora personas y recupera búsquedas recientes o fijadas.
---

Arranca el bot con la [instalación en el NAS](../start/install.md#configura-un-nas-con-telegram) o ejecuta `.venv/bin/python scripts/run_bot.py` en su propia terminal.

1. Envía `/start` y elige un idioma. Puedes cambiarlo con `/settings`.
2. Si el bot te pide un código, usa el código de acceso actual. El bot muestra un código de seis cifras para lectores al arrancar, salvo que hayas configurado `TELEGRAM_ACCESS_CODE`. Un propietario o administrador también puede emitir una invitación temporal.
3. Prueba `dame 3 fotos de playa de 2021`, `/folders 2021-2023` o **Personas**.

| Para | Usa |
| --- | --- |
| Listar años y álbumes | `/years [YYYY-YYYY]`, `/folders <consulta>` |
| Ver fotos | `/images [cantidad] <consulta>`, `/random [cantidad] [consulta]`, `/more [cantidad]` |
| Acotar la última búsqueda | `/refine antes de 2020` o un mensaje de seguimiento. Si tienes que elegir, usa `/refine album <ruta>`. |
| Explorar personas y álbumes vinculados | `/people`, `/people show <nombre-o-alias>` |
| Recuperar una búsqueda | **Búsquedas recientes**, **Búsquedas fijadas**, `/recent`, `/pinned` |
| Ver una cronología | `/timeline 2024 \| Cartagena` o `/timeline 2024-06-01..2024-08-31 \| Cartagena` |
| Comprobar el bot y el índice | `/whoami`, `/stats`, `/help` |

Las tandas de fotos indican si incluyen varias carpetas y ofrecen un botón para elegir una. El progreso y el historial se guardan por chat entre reinicios. La ficha de una persona puede mostrar fotos de álbumes vinculados. El motivo `album_person="Name"` señala un vínculo con el álbum.

## Comandos de propietario y administrador

```text
/people add <display-name>
/people alias <canonical> | <alias>
/people rename <canonical> | <new-display-name>
/people link <canonical> | <folder-path>
/people unlink <canonical> | <folder-path>
/album <path> | title | <new title>
/invite [viewer|admin] [days]
/invite list
/invite revoke <code>
/authorized
/authorized role <chat-id> <viewer|admin|owner>
/authorized revoke <chat-id>
```

Las fichas de personas ofrecen las mismas acciones de edición mediante botones. Usa la ruta exacta que muestra `/folders`. Con `/album`, omite el campo para ver los detalles o usa `date` (AAAA-MM-DD), `note`, `place` o `aliases` (uno por línea). Deja el valor vacío para borrarlo.

Los lectores pueden buscar y explorar. Los administradores editan personas y gestionan el acceso de los lectores. El propietario también gestiona a los administradores y cambia los roles dinámicos. Los lectores y propietarios estáticos se definen en las listas de la configuración. Los lectores dinámicos pueden salir con `/logout`.

Las fotos pedidas al bot se envían por Telegram. Para explorar el archivo dentro de tu red usa el [navegador local](./family.md).
