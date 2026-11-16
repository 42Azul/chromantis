---
title: Pruebas de búsqueda local
description: Interpretación opcional de consultas, OCR y pruebas de búsqueda visual.
---

## Intérprete opcional con un modelo local

La API y Telegram usan el intérprete por reglas. Para probar un modelo local, define un comando en `.env`, por ejemplo `QUERY_INTERPRETER_COMMAND=/opt/chromantis/bin/model-adapter`, y reinicia ambos clientes. El ejecutable recibe un objeto JSON UTF-8 por stdin y debe escribir uno por stdout. Envía los diagnósticos a stderr.

| Dirección | Ejemplo |
| --- | --- |
| Stdin | `{"text":"Find a couple of city photos from 2021"}` |
| Stdout | `{"action":"images","query":"city 2021","count":2,"confidence":0.9}` |

Las acciones son `images`, `folders`, `random` y `years`. Se admiten cantidades de 1 a 10 y confianzas de 0 a 1. Si la confianza es inferior a 0,65, se pide una aclaración. Si el adaptador falla, se agota el tiempo o la respuesta es inválida, se usan las reglas. El adaptador recibe el texto de la consulta. El buscador aplica el resultado al índice existente.

También se puede implementar `QueryInterpreter.interpret(text)` y pasar el adaptador a `ApplicationService` para ejecutarlo en el mismo proceso.

## Enriquecimiento opcional de imágenes

Ejecuta el enriquecimiento después de indexar. La CLI solo lee fotos indexadas de la fuente configurada y guarda los resultados del modelo en otra tabla SQLite junto con el modelo, versión, metadatos de origen y hora de procesamiento. Omite fotos ya procesadas por esa versión, reintenta los fallos después de las fotos pendientes e ignora resultados obsoletos si cambian los metadatos de origen.

El adaptador de OCR requiere Tesseract y los datos del idioma elegido. Empieza con un lote pequeño:

```bash
python scripts/enrich_images.py \
  --command "python scripts/tesseract_enricher.py --language eng" \
  --model tesseract-eng --version "$(tesseract --version | head -n 1)" --limit 25
```

Añade `--album "2024/2024-08-04_beach"` para limitar el lote a una ruta de álbum exacta. Vuelve a ejecutar el mismo comando para continuar con las fotos pendientes de ese álbum y versión.

Para descripciones o etiquetas de objetos, indica un adaptador de imágenes en `--command`. Cada ejecución recibe los bytes de un original por stdin y emite un objeto JSON UTF-8 por stdout. Devuelve cadenas o listas vacías para los campos que el modelo no proporcione.

```json
{"caption":"A bicycle beside a blue wall","ocr_text":"BIKE SHOP","object_tags":["bicycle","wall"]}
```

Pon `ENRICHMENT_SEARCH=true` y reinicia la API y el bot para incluir estos campos en la búsqueda de imágenes, incluida la aleatoria. Los resultados explican los términos que coincidieron gracias al modelo. Los filtros de año y persona se siguen aplicando. Por defecto se buscan metadatos indexados sin ejecutar un modelo.

### Evalúa la búsqueda con fotos sintéticas

Con Pillow, el comando crea un archivo de fotos temporal y una base SQLite. Ejecuta 13 consultas sobre nueve imágenes sintéticas e informa de coincidencias exactas y cobertura entre los cinco primeros resultados, fallos por consulta y latencia mediana y p95. Añade `--ocr` para comparar con Tesseract y sus datos de inglés. La prueba siempre usa su propio archivo y no depende de la configuración local.

```bash
python scripts/evaluate_search.py --ocr
```

Con Tesseract 5.5.0, leer las nueve imágenes tomó unos 1,8 segundos. Coincidencias exactas entre los cinco primeros resultados:

| Tipo de consulta | Metadatos indexados | Metadatos y OCR |
| --- | ---: | ---: |
| Álbum, persona, lugar o fecha | 4/4 | 4/4 |
| Texto escrito | 0/4 | 4/4 |
| Objetos o escenas | 0/4 | 0/4 |
| Objeto ausente | 1/1 | 1/1 |

Las consultas de texto incluyen carteles repetidos en distintos álbumes y años. Los tiempos de consulta usan campos ya indexados en SQLite. El tiempo de preparación mide la ejecución del OCR sobre ilustraciones sintéticas pequeñas.

### Prueba de búsqueda visual local

Ejecuta esta prueba en un ordenador con Pillow, NumPy, ONNX Runtime y Tokenizers. Guarda `tokenizer.json`, `onnx/vision_model_quantized.onnx` y `onnx/text_model_quantized.onnx` de la revisión fijada en el mismo directorio local, con los nombres sin el prefijo `onnx/`. El script verifica los hashes antes de cargar el modelo. [Archivos del modelo](https://huggingface.co/Xenova/clip-vit-base-patch32/tree/6ef1ebc8b0766a7a8d11b146462c99cdf74dd22d)

```bash
python scripts/evaluate_visual_search.py /path/to/local/model
```

El script compara la búsqueda ordinaria, un vocabulario bilingüe breve de etiquetas y la similitud entre imagen y texto. Reutiliza las ilustraciones sintéticas, añade una paráfrasis, combina un nombre con un año y comprueba un color y un entorno incorrectos. Crea su propio índice temporal. El vocabulario se ajustó a los conceptos ilustrados.

Con el umbral de similitud de 0,28, la prueba en x86-64 produjo estas coincidencias exactas:

| Grupo de consultas | Metadatos indexados | Etiquetas del vocabulario | Similitud imagen-texto |
| --- | ---: | ---: | ---: |
| Consultas visuales originales | 0/4 | 4/4 | 1/4 |
| Consulta adicional en inglés con persona y año | 0/1 | 1/1 | 1/1 |
| Nueva paráfrasis | 0/1 | 0/1 | 1/1 |
| Color o entorno erróneo descartado correctamente | 2/2 | 2/2 | 0/2 |

Los tres métodos acertaron las cuatro consultas de metadatos. El modelo ocupa unos 149 MiB. La prueba con ONNX Runtime 1.32 alcanzó unos 275 MiB de memoria RSS y tardó unos 0,45 segundos en generar cada conjunto de datos para nueve dibujos. La latencia mediana fue de unos 0,65 ms con etiquetas guardadas y 4,4 ms con la similitud que calcula el vector del texto al consultar. Sin contar la sobrecarga, las etiquetas ocupaban 208 bytes y los vectores en memoria, 18 KiB. En esta prueba las etiquetas cabían en las páginas SQLite existentes. Las mediciones corresponden al entorno sintético x86-64. El experimento funciona sin conexión y el uso normal no requiere modelos.
