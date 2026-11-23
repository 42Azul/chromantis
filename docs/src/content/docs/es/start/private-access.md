---
title: Acceso privado
description: Abre la web del NAS, invita a tu familia y comparte un solo álbum.
---

## Abre la web del NAS desde tu ordenador

Ejecuta el comando en el ordenador donde quieras abrir el navegador:

```bash
ssh -N -L 8787:127.0.0.1:8787 user@nas
```

Abre [http://127.0.0.1:8787/](http://127.0.0.1:8787/) y deja esa terminal abierta. Añade `-p PUERTO` si SSH usa un puerto personalizado. Si el puerto local 8787 está ocupado, cambia el primero del comando y el de la dirección del navegador.

Para entrar habitualmente desde la Wi-Fi de casa, usa un proxy inverso HTTPS local con un certificado de confianza para tus dispositivos. Chromantis admite HTTP sin cifrar solo desde la interfaz de bucle local y con un nombre local, como en el túnel SSH de arriba. El acceso por red requiere HTTPS y [autenticación de la API](#configura-un-token-de-propietario).

Si un proxy inverso en la misma máquina termina HTTPS, conserva `API_BIND_HOST=127.0.0.1` y añade `API_TRUST_LOCAL_PROXY=true` en `.env`. Reinicia la API. Configura el proxy para servir HTTPS en la red privada, conservar la cabecera `Host` original con su puerto y sobrescribir `X-Forwarded-Proto` con el protocolo real. Redirige HTTP en el propio proxy. La API solo confía en esa cabecera desde la interfaz de bucle local y con esta opción activada. Si ya usabas un proxy HTTPS, aplica estos ajustes al actualizar.

## Configura un token de propietario

El instalador del NAS crea un token de propietario. Para configurar el acceso manualmente, pon el ID del chat propietario en `TELEGRAM_ADMIN_CHAT_ALLOWLIST` y un token generado para ese ID en `API_CHAT_TOKENS`.

```dotenv
TELEGRAM_ADMIN_CHAT_ALLOWLIST=123456789
API_CHAT_TOKENS={"123456789":"replace-with-generated-token"}
```

Reinicia la API e introduce ese token en el navegador. El propietario puede gestionar el acceso y compartir álbumes. El token compartido `API_TOKEN` solo permite leer. Para que un lector autorizado pueda etiquetar desde el navegador con su propio token, añade su ID a `API_CURATOR_CHAT_IDS` y reinicia la API.

## Invita a un familiar sin Telegram

Con la autenticación de la API activada, ejecuta en el NAS:

```bash
.venv/bin/python scripts/family_access.py invite "Family tablet"
.venv/bin/python scripts/family_access.py list
.venv/bin/python scripts/family_access.py revoke 1
```

Envía el código en privado. El familiar abre la dirección local de Chromantis, elige **Acceso familiar** e introduce el código en las 24 horas siguientes. La sesión dura hasta 90 días en ese navegador y permite buscar y etiquetar álbumes sin permisos de administrador. Usa el ID que muestra `list` para revocar la sesión. Genera un código nuevo si cambia de navegador o cierra sesión.

### Recupera el acceso tras perder un dispositivo

Usa `list` en el NAS para identificar la invitación o sesión de ese dispositivo y revoca su ID. La revocación bloquea las siguientes solicitudes protegidas. Después, genera un código de un solo uso para el dispositivo nuevo. Usa etiquetas distintas si una persona accede desde varios dispositivos.

Chromantis guarda en SQLite los hashes de los secretos de invitación y sesión. Al canjear el código se sustituye por un secreto de sesión nuevo. Trátalo como una contraseña hasta que caduque o se revoque. El navegador usa una cookie limitada al host con `HttpOnly`, `SameSite=Strict` y `Secure` en HTTPS, y el servidor verifica el origen exacto de las escrituras familiares. Android conserva la sesión localmente con cifrado de Android Keystore. El acceso familiar permite buscar y etiquetar en el archivo. Usa un enlace de álbum si el destinatario solo debe ver un álbum.

## Comparte un solo álbum

1. Entra como propietario y abre el álbum en **Archivo** (*Archive*).
2. Pulsa **Compartir álbum** y copia el enlace cuando aparezca.
3. Envíalo en privado a alguien que ya pueda acceder al servidor de Chromantis.

El enlace caduca a los siete días. Quien lo tenga puede ver el álbum y sus detalles hasta que caduque o lo revoques. Pulsa **Revocar** para bloquear la siguiente solicitud de la galería, una miniatura o un original. El acceso se limita a ese álbum y funciona a través de la red privada o el túnel que ya usas.
