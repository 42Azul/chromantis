---
title: Prueba de MCP de solo lectura
description: Evalúa herramientas MCP limitadas a un álbum con SQLite y un archivo sintético.
---

Chromantis tiene un núcleo MCP para evaluar la búsqueda en un álbum sin exponer el NAS ni ejecutar un modelo en segundo plano. Puede integrarse más adelante con distintos mecanismos de conexión.

## Alcance y privacidad

- `chromantis_list_album` devuelve los metadatos editados del álbum concedido y una lista limitada de nombres de archivo.
- `chromantis_search_album` busca solo en esos metadatos y nombres.
- La autorización reutiliza el permiso revocable y temporal de un álbum compartido. SQLite conserva su hash y se comprueba que sigue vigente en cada llamada.
- Los argumentos de las herramientas no pueden elegir otro álbum. Solo se puede ver el que autoriza el permiso.
- No hay herramientas de escritura ni acceso a miniaturas u originales. Las respuestas omiten rutas y direcciones del archivo.
- La prueba solo lee SQLite y funciona con el archivo desconectado.

El núcleo no abre puertos ni añade dependencias. Ofrece definiciones y resultados compatibles con MCP. Una futura capa de conexión puede usarlo conservando en `app/` la autorización y la lógica de búsqueda.

## Conexión

En esta prueba no hay un servidor MCP accesible. Antes de añadir una conexión, comprueba los requisitos oficiales del cliente y la versión de Python que admite el SDK elegido. Una conexión remota seguiría siendo opcional y requiere evaluar disponibilidad, autenticación, privacidad, coste en el NAS y si resuelve una necesidad familiar concreta.

- [Conectar servidores MCP personalizados en ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [SDK oficial de MCP para Python](https://py.sdk.modelcontextprotocol.io/v2/)

## Reproduce la prueba

```bash
python -m unittest tests.test_mcp_readonly -v
```

La prueba crea dos álbumes sintéticos, concede acceso a uno, desconecta el archivo, lista y busca en el álbum autorizado, comprueba que el otro queda fuera, rechaza una operación de escritura y verifica que la revocación surte efecto de inmediato.
