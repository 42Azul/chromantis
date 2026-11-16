---
title: Android · versión preliminar
description: Compila el APK nativo en Kotlin y Compose y pruébalo a través de HTTPS privado.
---

Chromantis para Android está en versión preliminar y requiere Android 8.0 o posterior. Se conecta a tu propio servidor de Chromantis por HTTPS privado y usa un [código de acceso familiar](../start/private-access.md#invita-a-un-familiar-sin-telegram).

**Cómo conseguir el APK.** Compílalo desde el código fuente siguiendo estos pasos. Todavía no hay un APK público listo para descargar.

## Qué puedes hacer

- **Carpetas** muestra años, álbumes y una galería paginada. Si el servidor tiene miniaturas activadas, la app carga las visibles. Toca una foto para abrir el original. Toca **Carpetas**, el año o el álbum en la ruta para volver a ese nivel. **Continuar en…** abre la última galería visitada desde Carpetas en la última página que se cargó. El acceso directo se guarda en el dispositivo y se borra cuando termina la sesión familiar.
- **Clasificar** muestra una tarjeta por álbum. Desliza a la derecha para aceptar la etiqueta que ves o a la izquierda para dejar el álbum pendiente. También puedes pulsar los botones. En **Personas, fotos y etiquetas** puedes buscar personas por nombre o alias, ver algunas fotos bajo demanda o corregir decisiones. Para editar un álbum ya revisado, abre **Etiquetar este álbum** en la galería.
- **Buscar** empieza con palabras del álbum o el nombre de una persona. Escribe después `antes de 2020` o `con Ana` para acotar esos resultados. Si el nombre del álbum es ambiguo, elige uno de los candidatos. Se usan las reglas de búsqueda locales.

En **Ajustes** puedes elegir claro, oscuro o seguir el tema de Android. La elección se guarda en el dispositivo.

## Etiqueta fotos individuales

1. Abre una galería y pulsa **Seleccionar fotos** o mantén pulsada una foto. Marca las fotos de la página actual.
2. Pulsa **Etiquetar fotos**. Elige **Añadir** o **Quitar** y selecciona una persona existente por su nombre o alias, escribe una etiqueta de una sola palabra o haz ambas cosas. Confirma para aplicar el cambio a la selección. Puedes salir con Atrás antes de guardar.
3. En **Buscar → Fotos por persona**, escribe un nombre o alias. Aparecerán las fotos en las que se haya confirmado esa persona. La búsqueda de álbumes sigue incluyendo los vínculos al álbum.

Para editar necesitas permiso de etiquetado. Si una foto indexada cambia durante la edición, actualiza la galería y vuelve a seleccionar las fotos.

Con las miniaturas activadas, **Revisar foto a foto** te deja elegir a una persona y recorrer la página actual de la galería. Desliza a la derecha para marcar la foto o a la izquierda para saltarla. Los botones hacen lo mismo. **Deshacer última decisión** vuelve a la foto anterior. **Guardar** aplica los vínculos nuevos en un solo lote. Salir de la revisión descarta el borrador. Si una miniatura falla, puedes saltar la foto.

Falta probar el recorrido completo en un teléfono físico actual. El cliente nativo de `android/` usa Kotlin y Jetpack Compose con Material 3. El servicio compartido gestiona el acceso al archivo, los permisos, la indexación y el etiquetado.

## Compila e instala

En tu ordenador necesitas JDK 17 o 21, Gradle 8.13, Android SDK Platform 36 y Build Tools 36.0.0. Apunta `ANDROID_HOME` al SDK. Desde la raíz del repositorio:

```bash
gradle -p android spotlessCheck testDebugUnitTest assembleDebug lintDebug
adb install -r android/build/outputs/apk/debug/Chromantis-debug.apk
```

El APK de depuración se firma con la clave de depuración local. Ábrelo con una dirección HTTPS privada a la que llegue el móvil y un código familiar. Si usas un proxy inverso para HTTPS, conserva la cabecera `Host` original en las solicitudes de la sesión familiar. HTTP sin cifrar está desactivado. El APK de depuración admite certificados instalados por el usuario para las pruebas locales. El APK de distribución usa los certificados de confianza del sistema. Para formatear el código Kotlin con la versión fijada de ktfmt, ejecuta `gradle -p android spotlessApply`.

## Firma un APK para distribuirlo en privado

Crea una clave de firma una sola vez y guárdala fuera del repositorio. Copia `android/keystore.properties.example` a `android/keystore.properties`. Indica la ruta absoluta de la clave y sustituye los valores de ejemplo. Git ignora el archivo de configuración y los archivos `.jks` y `.keystore`. Compila y verifica el resultado:

```bash
keytool -genkeypair -v -keystore /private/path/to/chromantis-release.jks \
  -alias chromantis -keyalg RSA -keysize 3072 -validity 10000
gradle -p android spotlessCheck testDebugUnitTest assembleRelease lintRelease
apksigner verify --verbose android/build/outputs/apk/release/Chromantis-release.apk
```

Guarda una copia privada del almacén de claves y de las contraseñas. Para instalar una actualización en Android necesitas firmarla con la misma clave. En CI u otro equipo de confianza puedes prescindir de `keystore.properties` y definir `CHROMANTIS_KEYSTORE_PATH`, `CHROMANTIS_KEYSTORE_PASSWORD`, `CHROMANTIS_KEY_ALIAS` y `CHROMANTIS_KEY_PASSWORD`. Si Gradle no encuentra `assembleRelease`, comprueba que los cuatro valores estén configurados. Sin ellos se desactiva la variante de distribución y el comando general `assemble` solo genera el APK de depuración.

## Prueba con un archivo sintético

Para probar en un emulador, instala el extra de miniaturas, que incluye Pillow. Genera un certificado temporal para el alias del anfitrión y ejecuta el ejemplo sin el NAS:

```bash
fixture_dir=$(mktemp -d)
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=Chromantis-Fixture \
  -addext 'subjectAltName=IP:10.0.2.2' \
  -keyout "$fixture_dir/key.pem" -out "$fixture_dir/cert.pem"
PYTHONPATH=src python tests/android_fixture.py \
  --cert "$fixture_dir/cert.pem" --key "$fixture_dir/key.pem"
```

Instala el certificado temporal como CA de usuario de confianza en un emulador de pruebas. Usa la dirección `https://10.0.2.2:8443` y el código de un solo uso que imprime el ejemplo. Abre 2024, pasa a la segunda página de la galería, abre una foto y gira el dispositivo. Comprueba que sigue abierta la misma foto y que al volver atrás aparece la segunda página. Relanza la app para comprobar que conserva la sesión.

En **Clasificar**, desliza la primera tarjeta a la izquierda y usa **Volver al principio** al final de la cola para recuperarla. Abre **Personas, fotos y etiquetas**, filtra por `Anita`, selecciona a Ana y guarda. En **Buscar**, busca `Ana` y afina con `solo 2024` para encontrar el álbum.

Repite con un ejemplo nuevo en modo `--index-only`. Desliza a la derecha sobre una etiqueta sugerida. La app muestra la siguiente sugerencia del mismo álbum o pasa al siguiente cuando terminas. Abre el álbum desde **Carpetas** y comprueba la decisión en **Etiquetar este álbum**. Prueba los botones y los gestos con el archivo sintético desconectado.

Para comprobar el etiquetado individual, selecciona las fotos 1 y 3 del álbum de 2024 y añade a Ana. Busca `Anita` en **Fotos por persona** y comprueba que salen exactamente esas dos. Quita a Ana de la primera y repite la búsqueda. Solo debería aparecer la tercera. Pulsa Ctrl+C para eliminar el índice temporal y las fotos sintéticas.

Para probar los gestos, arranca un ejemplo nuevo con el archivo sintético conectado. En **Revisar foto a foto**, elige a Ana, marca la foto 1, salta la 2, marca la 3, deshaz la última decisión y salta la 3. Guarda y comprueba que la búsqueda confirmada devuelve solo la foto 1. Repite con el editor por lotes y compara el tiempo y los errores de selección.

Para comprobar la ruta de carpetas, abre la segunda página de la galería de 2024 y entra en una foto. Toca el álbum en la ruta para volver a la segunda página y luego **Carpetas** para llegar a la lista de años en un toque. Cierra y vuelve a abrir la app y usa **Continuar en…** para regresar a la segunda página. Si al reindexar se eliminó esa página, el acceso directo abre la primera disponible.
