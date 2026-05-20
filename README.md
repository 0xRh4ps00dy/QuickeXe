# QuickeXe

QuickeXe es una aplicacion web con FastAPI para convertir archivos **DOCX** y **PDF** en paquetes compatibles con **eXeLearning**. Permite previsualizar el contenido extraido, generar un ZIP para descargar o guardar varios paquetes directamente en un directorio de salida.

## Que hace

- Convierte documentos `.docx` y `.pdf` a un paquete `.zip` con la estructura que espera eXeLearning.
- Extrae paginas y contenido desde documentos con texto digital.
- Conserva imagenes y recursos incrustados en DOCX cuando el parser los detecta.
- Ofrece una previsualizacion HTML antes de convertir.
- Permite elegir una carpeta de salida para guardar uno o varios paquetes.

## Requisitos

- Python 3.12 o superior.
- Dependencias instaladas desde `requirements.txt`.
- Para usar el contenedor, Docker y Docker Compose.

## Instalacion local

1. Crear y activar un entorno virtual.
2. Instalar dependencias:

```bash
pip install -r requirements.txt
```

## Ejecutar en local

Inicia la aplicacion con Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Luego abre `http://127.0.0.1:8000`.

## Ejecutar con Docker

Con Docker Compose:

```bash
docker compose up --build
```

La aplicacion queda disponible en `http://127.0.0.1:8888`.

## Uso

1. Abre la pagina principal.
2. Sube uno o varios archivos `.docx` o `.pdf`.
3. Si cargas varios archivos, indica un directorio de salida.
4. Opcionalmente, usa la previsualizacion para revisar el contenido antes de convertir.
5. Descarga el ZIP o revisa los archivos guardados en la carpeta elegida.

## API

La aplicacion expone estos endpoints principales:

- `GET /` muestra la interfaz web.
- `POST /preview` genera una vista previa del documento subido.
- `POST /convert` convierte uno o varios archivos a paquetes eXeLearning.
- `GET /directories` lista carpetas para el selector de salida.

## Restricciones y comportamiento

- Solo se aceptan archivos `.docx` y `.pdf`.
- El tamano maximo por archivo es de 50 MB.
- Los PDF deben tener texto digital; no se procesa OCR.
- En DOCX, el contenido se divide por encabezados de nivel 1 cuando existen.
- En PDF, se genera una pagina por pagina del documento.

## Estructura del proyecto

```text
app/
  main.py                  # API FastAPI y rutas web
  converter/               # Parsers y generador del paquete
  exe_base/                # Assets base para el paquete eXeLearning
  static/                  # CSS y JS de la interfaz
  templates/               # Plantilla HTML principal y plantillas del paquete
test_web/                  # Material de prueba y referencias de exportacion
```

## Notas tecnicas

- El paquete final replica la estructura que eXeLearning espera al importar una exportacion web.
- Los recursos embebidos se copian a `content/resources/` dentro del ZIP.
- La interfaz web incluye una vista previa basada en los mismos datos usados para la conversion.

## Licencia

No se ha definido una licencia en el repositorio.