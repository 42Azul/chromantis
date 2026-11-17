---
title: Explorar y etiquetar álbumes
description: Encuentra fotos familiares, revisa álbumes y guarda correcciones desde el navegador.
---

Abre la dirección local de Chromantis e [inicia sesión](../start/private-access.md). Puedes usar un móvil o un ordenador.

Las capturas muestran la web en una pantalla de tamaño móvil con un archivo de ejemplo.

## Encuentra un álbum

En una sesión familiar, abre **Buscar álbumes** para navegar por año o buscar por palabras de la carpeta, título, alias, lugar o persona. Prueba `playa 2024` o `Ana`. Abre un álbum para ver sus fotos y usa el visor para abrir o descargar un original. La [caché opcional de miniaturas](../operate/maintenance.md#carga-miniaturas-solo-cuando-hagan-falta) aligera la galería en el móvil.

Usa la cronología para buscar por lugar o fecha. La fecha puede venir de la carpeta indexada o de una corrección guardada. Si están disponibles, el visor indica por separado la fecha de captura y la de modificación del archivo.

Puedes acotar la búsqueda con `antes de 2020`, `solo 2019` o `con Ana`. Si coinciden varios álbumes, elige uno. Escribe una consulta nueva para empezar de cero. Prueba `fotos de la playa con Ana antes de 2020` para añadir persona y año a la vez. Pulsa **×** al lado del año, la persona o el álbum para quitar solo ese filtro.

![Búsqueda familiar en el móvil. Al buscar Ana aparece el álbum Un día en la playa.](../../../../assets/screenshots/web-search.webp)

## Etiqueta tu primer álbum

1. Abre **Etiquetar álbumes** y elige uno de los pendientes. Verás su título y la fecha, si se conoce.
2. Busca a **Ana** por nombre o alias y selecciónala. Puedes elegir a más personas o añadir una nueva. Si necesitas recordar quién aparecía, pulsa **Ver hasta 3 fotos**.
3. Acepta, rechaza o corrige las sugerencias del nombre de la carpeta. También puedes añadir etiquetas de una sola palabra.
4. Pulsa **Guardar y siguiente**. Abre **Buscar álbumes** y busca `Ana` para encontrar el álbum.

![Revisión de un álbum con Ana seleccionada, la sugerencia playa marcada como Aceptar y el botón Guardar y siguiente al pie.](../../../../assets/screenshots/web-tag.webp)

Para comprobar el álbum antes de guardar, pulsa **Ver hasta 3 fotos**. Toca una miniatura para abrir el original.

![Tres miniaturas del archivo de ejemplo tras pulsar Ver hasta 3 fotos en la revisión del álbum.](../../../../assets/screenshots/web-gallery.webp)

El vínculo indica que la persona aparece en alguna foto del álbum. Para marcar las fotos exactas en las que aparece, usa el [etiquetado por foto en Android](./android.md#etiqueta-fotos-individuales) o la [API de etiquetado por foto](../reference/api.md#etiquetado-manual-por-foto).

Pulsa **Saltar** si tienes dudas. Para corregir un vínculo en una sesión familiar, busca el título del álbum en **Buscar álbumes** y abre el resultado. Pulsa **Ana ×** entre las personas seleccionadas y después **Guardar y volver a resultados**. La búsqueda se actualiza y el álbum desaparece si ha dejado de coincidir. Pulsa **Volver a resultados** para salir del editor sin guardar los cambios de personas y etiquetas. También puedes abrir álbumes ya revisados desde **Ya revisados**.

## Revisa sugerencias por lotes

Abre **Por lotes** para agrupar álbumes con la misma sugerencia. Cada sugerencia muestra la palabra del nombre de carpeta que la originó. Puedes aceptarla en unos álbumes, rechazarla en otros y dejar pendientes los dudosos. Pulsa **Revisar** para hacer correcciones individuales. Usa **Guardar y volver al lote** para aplicar la corrección o **Volver a Por lotes** para volver sin guardarla. Se recuperan las selecciones del lote que sigan vigentes. En un grupo, **Aceptar los pendientes** y **Rechazar los pendientes** rellenan solo las filas que aún no has decidido. Comprueba el recuento y ajusta las filas que quieras antes de pulsar **Guardar decisiones**.

El grupo se guarda de una vez. Al guardar, las selecciones de otros grupos se conservan si la sugerencia sigue pendiente y la revisión del álbum coincide con la esperada. Si el guardado se completa pero falla la recarga, pulsa **Reintentar la carga** para actualizar la cola y recuperar esas selecciones. Si la cola avisa de que una selección ha cambiado, revísala antes de guardar. Este flujo solo usa los nombres guardados en SQLite. Las decisiones y las etiquetas manuales se conservan al reindexar si la ruta sigue siendo la misma. Una carpeta trasladada o renombrada se indexa como un álbum nuevo. Las palabras del nombre original siguen encontrando el álbum aunque rechaces una sugerencia.

## Edita los detalles del álbum

Abre **Detalles del álbum** para añadir una nota, un lugar o hasta ocho alias, o para corregir el título y la fecha. Borra una corrección para volver al valor indexado. El año corregido se usa para navegar por años. Puedes seguir buscando por el nombre original de la carpeta o por otros nombres.

## Guarda una colección privada

Con una sesión de propietario, usa **Add photo to collection** o **Add album to collection** y elige una colección o crea una. En **Collections** puedes volver a las entradas y quitarlas. Cada propietario tiene sus propias colecciones, con un máximo de 100 colecciones y 250 entradas por colección. Una entrada vuelve a estar disponible si el índice recupera la misma ruta y raíz del archivo.

Para que otra persona pueda ver un álbum, usa un [enlace revocable](../start/private-access.md#comparte-un-solo-álbum).
