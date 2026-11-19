---
title: Browse and tag albums
description: Find family photos, review albums, and save corrections in the local browser.
---

Open the local Chromantis address and [sign in](../start/private-access.md). The browser works on a phone or computer.

Choose **Appearance** in the sidebar for **System**, **Light**, or **Dark**. In a family session, the control is labelled **Aspecto**. Your choice is saved on this browser. **System** follows the device appearance.

The screenshots show the browser on a phone-sized screen with a sample archive. The light-theme photo examples use blue tiles and fictional names.

## Find an album

In a family session, open **Buscar álbumes** to browse by year or search by folder words, title, alias, place, or person. Try `playa 2024` or `Ana`. Open an album for its photos and use the viewer to open or download an original. The [optional thumbnail cache](../operate/maintenance.md#load-small-previews-on-demand) keeps the grid light on mobile.

Choose **Explorar por año** to see the indexed years and their album and photo counts. Open a year, then an album. **Página siguiente** shows more albums and **Volver a años** returns to the year list. After reviewing an album, **Volver a resultados** restores the same page. This navigation works with the photo archive disconnected.

Use the album timeline to browse by place or date. A date can come from the indexed folder or a saved correction. The photo viewer shows camera-reported and file modification dates separately when available.

To narrow the current search, follow up with `before 2020`, `only 2019`, or `with Ana`. Choose an album if several match. A fresh query starts a new search. Try `fotos de la playa con Ana antes de 2020` to set a person and year at once. Tap **×** beside an active person, year, or album to remove just that filter.

![Family search on a phone. The query Ana returns Un día en la playa.](../../../assets/screenshots/web-search.webp)

## Find photos by person

Under **Buscar álbumes**, change the result type to **Fotos por persona** and search a name or alias. Results include individually tagged photos from the web or [Android](./android.md#tag-individual-photos). Use **Álbumes** to search by album links. Previews appear when the thumbnail cache is enabled. Tap a result to open its original.

Use **Etiqueta manual opcional** to narrow that person's photos to one manual photo tag. For example, search `Ana` with `romería`. Clear that field to see all photos confirmed for Ana again.

With a curator account, choose **Etiquetar foto** to add or remove people on that specific photo. The same action is available under **Ver fotos del álbum** in the album editor. Pick a name or alias and choose **Guardar cambios**. If you remove the person you were searching for, the photo leaves those results.

For a manual photo tag, choose **Fotos por etiqueta** and enter one exact tag such as `romería`. The search matches the whole tag and ignores accents and case. If you remove the tag from a result, that photo leaves the list.

To classify several search results together, choose **Seleccionar fotos**, mark only the photos you want, or use **Seleccionar esta página** and uncheck doubtful photos. **Etiquetar fotos** opens the same batch editor as the gallery. The batch can span albums; each result shows its album path and the editor includes paths to distinguish repeated filenames. Save once to add or remove people and manual tags. The search keeps its person, tag and page, returning to an earlier page if edits empty the current one. Canceling or changing pages clears the selection without saving. This flow also works from the index with previews disabled and the archive disconnected.

Choose **Ver álbum** on a photo result to open its album. **Volver a resultados** and **Guardar y volver a resultados** restore the same search and page.

## Tag your first album

1. Open **Tag albums** (*Etiquetar álbumes*) and select a pending album. Its title and known date appear first.
2. Search for **Ana** or a saved alias. Select her, choose other people, or add a new person. Use **Ver fotos del álbum** if you need a reminder.
3. Accept, reject, or correct the folder-name suggestions. You can also add one-word manual tags.
4. Choose **Save and next** (*Guardar y siguiente*). Open **Buscar álbumes** and search for `Ana` to find the album.

![Album review with Ana selected, the playa suggestion set to Accept, and the Save and next button at the bottom.](../../../assets/screenshots/web-tag.webp)

Choose **Ver fotos del álbum** to browse six photos at a time. Use **Más fotos** and **Fotos anteriores** to move through the album. When the thumbnail cache is off, start with filenames and use **Abrir foto** to load an original. Browsing keeps your unsaved album edits.

![Light-theme album gallery with six sample photos, Seleccionar fotos, Más fotos and Revisar foto a foto.](../../../assets/screenshots/web-gallery-current.png)

## Tag individual photos

To edit several photos together, choose **Seleccionar fotos**, mark the photos on the current page, then choose **Etiquetar fotos**. Review the filenames and pick the people to add or remove. Under **Etiquetas manuales**, enter one-word tags separated by commas or mark existing tags for removal. Save once to apply the changes to the selected photos. You can use **Etiquetas manuales** on a single photo too. Changing pages clears the photo selection.

![Editor for Photo-01.jpg and Photo-03.jpg, with Luis selected, two manual tags entered, and Guardar en 2 fotos.](../../../assets/screenshots/web-photo-batch.png)

## Review one photo at a time

With thumbnails enabled, **Revisar foto a foto** reviews the current gallery page for one person. Choose their name or alias and press **Empezar**. Swipe right or use **Sí, aparece** to mark a visible photo. Swipe left or use **Saltar** to leave it for another pass. **Deshacer** revisits the previous decision. Check the marked filenames and choose **Guardar revisión** at the end. Closing before saving discards this review.

![Photo review asking whether Luis appears, showing one marked photo and the Saltar, Sí, aparece and Deshacer buttons.](../../../assets/screenshots/web-photo-review.png)

An album link records that someone appears somewhere in the album. To mark the exact photos where someone appears, use **Etiquetar foto** or [individual photo tagging in Android](./android.md#tag-individual-photos).

Use **Saltar** to leave a doubtful album pending. To correct a link in a family session, find the album by its title in **Buscar álbumes** and open the result. Tap **Ana ×** under the selected people, then choose **Guardar y volver a resultados**. The search refreshes and the album drops out if it no longer matches. Choose **Volver a resultados** to leave the editor without saving your people and tag changes. You can also open reviewed albums from **Ya revisados**.

## Review suggestions in batches

Open **Batch review** (*Por lotes*) to group albums by a repeated suggestion. Every suggestion shows the matching word from the folder name. Accept it for some albums, reject it for others, and leave uncertain ones pending. Use **Review** (*Revisar*) for individual corrections. Choose **Guardar y volver al lote** to save the correction or **Volver a Por lotes** to return without saving it. Your batch selections are restored if they are still valid. In a group, **Aceptar los pendientes** and **Rechazar los pendientes** fill only the rows you have left undecided. Check the count and adjust any row before choosing **Guardar decisiones**.

The group saves together. Selections in other groups stay selected after saving when the suggestion is still pending and the album has the expected revision. If the save succeeds but the queue fails to load, use **Reintentar la carga** to recover those selections and refresh the queue. If the queue reports that a selection changed, review it again before saving. This workflow uses the folder names in SQLite and requests no photos. Decisions and manual tags survive reindexing when the album path stays the same. A move or rename creates a new indexed album, and the original folder words remain searchable after a suggestion is rejected.

## Edit album details

Open **Album details** (*Detalles del álbum*) to add a note, place, or up to eight aliases, or to correct the title and date. Clear a correction to restore the indexed value. The corrected year is used for year browsing. Both the original folder title and alternate names remain searchable.

## Save a private collection

In an owner session, choose **Add photo to collection** or **Add album to collection**, then pick an existing collection or create one. Open **Collections** to revisit entries or remove them. Owners have separate collections, with up to 100 collections and 250 entries in each. An entry becomes available again when the same path and archive root return to the index.

To let someone else view an album, use a [revocable album link](../start/private-access.md#share-one-album).
