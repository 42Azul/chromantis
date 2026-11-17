---
title: Desarrollo y publicación
description: Ejecuta las pruebas, edita el Markdown y publica la documentación estática.
---

## Ejecuta las pruebas

Para desarrollar usa Python 3.10 o posterior y archivos sintéticos:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[telegram,thumbnails]'
.venv/bin/python -m unittest discover -s tests -v
node tests/test_album_review_ui.cjs
node tests/test_confirmed_photo_ui.cjs
```

El servicio Python está en `src/chromantis`. Los adaptadores y la interpretación de rutas alimentan el índice SQLite. La búsqueda y el etiquetado viven en la capa de aplicación compartida por Telegram y HTTP. Escribe el código nuevo de Android en Kotlin y crea la interfaz con Jetpack Compose. Consulta la [guía de compilación y pruebas de Android](../use/android.md).

Lee las [normas de contribución](https://github.com/42Azul/chromantis/blob/main/AGENTS.md) y la [hoja de ruta](https://github.com/42Azul/chromantis/blob/main/PLANNING.md) en inglés. Mantén fuera de Git los datos del archivo real, los tokens de chat y las claves de firma.

## Edita la documentación

Crea o edita el original en inglés en `docs/src/content/docs/` y su traducción en español en la misma ruta relativa bajo `docs/src/content/docs/es/`. Así, el selector de idioma abre la misma guía. Da un título y una descripción a cada guía y añade las nuevas a la barra lateral de `docs/astro.config.mjs`. Enlaza los Markdown con rutas relativas. Astro las adapta para que funcionen en GitHub y en el sitio publicado.

Desde el repositorio, usa Node.js 24.22 o posterior:

```bash
npm --prefix docs ci
npm --prefix docs run dev
npm --prefix docs run check
```

La comprobación compila el sitio, crea el índice de búsqueda y verifica los enlaces internos y sus anclas. Abre en `/chromantis/` la dirección de la vista previa que indica la terminal.

## Publica en GitHub Pages

En el repositorio, elige **Settings → Pages → Build and deployment → Source → GitHub Actions**. Ejecuta **Documentation** desde **Actions** para publicar por primera vez. Los cambios en `docs/` de `main` disparan las siguientes compilaciones. El flujo solo sube la documentación estática compilada.

## Mueve el sitio a otro alojamiento estático

```bash
DOCS_SITE=https://docs.example.org DOCS_BASE=/ npm --prefix docs run check
```

Sirve `docs/dist/` desde el alojamiento elegido. Usa `DOCS_BASE=/alguna-ruta` si va en un subdirectorio. La compilación no necesita adaptador de servidor, base de datos ni conexión a una cuenta. Astro Starlight genera el HTML estático y el índice de búsqueda a partir de los Markdown.
