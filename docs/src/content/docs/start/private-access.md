---
title: Private access
description: Open the NAS locally, create family browser sessions, and share a single album.
---

## Open the NAS from your computer

Run this from the computer where you want to open the browser:

```bash
ssh -N -L 8787:127.0.0.1:8787 user@nas
```

Open [http://127.0.0.1:8787/](http://127.0.0.1:8787/) and keep that terminal running. Add `-p PORT` if SSH uses a custom port. If local port 8787 is busy, change the first port in the command and in the browser address.

For everyday use on home Wi-Fi, use a trusted local HTTPS reverse proxy and preserve the browser's `Host` header. Android requires a trusted HTTPS origin. A DNS name gives the NAS an address. HTTPS still needs a listener and a certificate valid for that name. Keep the Chromantis service on the private network.

## Configure an owner token

The NAS setup script creates an owner token for you. With a manual setup, set `TELEGRAM_ADMIN_CHAT_ALLOWLIST` to the owner chat ID and put an individually generated token for that ID in `API_CHAT_TOKENS`.

```dotenv
TELEGRAM_ADMIN_CHAT_ALLOWLIST=123456789
API_CHAT_TOKENS={"123456789":"replace-with-generated-token"}
```

Restart the API, then enter the individual token in the browser. Owners can manage access and share albums. A shared `API_TOKEN` is read-only. To let an authorized viewer curate through their own chat token, add their ID to `API_CURATOR_CHAT_IDS` and restart the API.

## Invite a family member without Telegram

With API authentication enabled, run on the NAS:

```bash
.venv/bin/python scripts/family_access.py invite "Family tablet"
.venv/bin/python scripts/family_access.py list
.venv/bin/python scripts/family_access.py revoke 1
```

Send the one-time code privately. On the device, open the local Chromantis address, choose **Family access** (*Acceso familiar*) and enter the code within 24 hours. The session lasts up to 90 days in that browser and allows search and album review without administrator privileges. Use the ID shown by `list` to revoke a session. Issue a new code for another browser or after sign-out.

## Share one album

1. Sign in as owner and open the album in **Archive**.
2. Choose **Share album** (*Compartir álbum*) and copy the link when it appears.
3. Send it privately to someone who can already reach your Chromantis server.

The link expires in seven days. Anyone holding it can view that album and its details until expiry or revocation. Choose **Revoke** (*Revocar*) in the same panel to block the next gallery, thumbnail, or original request. Sharing an album grants access only to that album, through your existing private network or tunnel.
