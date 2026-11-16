---
title: Android · versión preliminar
description: Compila el APK nativo en Kotlin y Compose y pruébalo a través de HTTPS privado.
---

Chromantis para Android está en versión preliminar y requiere Android 8.0 o posterior. Se conecta a tu propio servidor de Chromantis por HTTPS privado y usa un [código de acceso familiar](../start/private-access.md#invita-a-un-familiar-sin-telegram).

**Cómo conseguir el APK.** Compílalo desde el código fuente siguiendo estos pasos. Todavía no hay un APK público listo para descargar.

## Qué puedes hacer

En **Carpetas** puedes explorar años y álbumes, buscar en el índice y abrir una galería paginada. Si el servidor tiene miniaturas activadas, la app carga las que necesitas para ver la galería. Toca una foto para abrir el original.

Entra con un código familiar de un solo uso. Abre **Etiquetar álbumes** para revisar los pendientes o **Etiquetar este álbum** desde la galería para corregirlo. Puedes buscar personas por nombre o alias, añadirlas o quitar su vínculo y decidir sobre las etiquetas sugeridas a partir del nombre de la carpeta. Pulsa **Ver hasta tres fotos** si necesitas una vista previa. Si saltas el álbum, queda pendiente.

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

Guarda una copia privada del almacén de claves y de las contraseñas. Para instalar una actualización en Android necesitas firmarla con la misma clave. En CI u otro equipo de confianza puedes prescindir de `keystore.properties` y definir `CHROMANTIS_KEYSTORE_PATH`, `CHROMANTIS_KEYSTORE_PASSWORD`, `CHROMANTIS_KEY_ALIAS` y `CHROMANTIS_KEY_PASSWORD`. La compilación de distribución se detiene si falta parte de la configuración de firma.

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

Instala el certificado temporal como CA de usuario de confianza en un emulador de pruebas. Usa la dirección `https://10.0.2.2:8443` y el código de un solo uso que imprime el ejemplo. Abre 2024, pasa a la segunda página de la galería, abre una foto, vuelve atrás y relanza la app para comprobar que conserva la sesión.

En **Carpetas**, abre **Etiquetar álbumes**, filtra por `Anita`, selecciona a Ana y guarda. Vuelve a **Carpetas** y busca `Ana`. Abre la galería y pulsa **Etiquetar este álbum** para retirar el vínculo o comprobar las decisiones guardadas. Repite la prueba con `--index-only` para comprobar que la navegación, los nombres y la edición de álbumes siguen funcionando con el archivo sintético desconectado. Pulsa Ctrl+C para eliminar el índice temporal y las fotos sintéticas.
