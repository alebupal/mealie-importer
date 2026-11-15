# Mealie Importer Web

Panel web interactivo para extraer recetas desde vídeos de **TikTok**, **Instagram** y **YouTube Shorts** e importarlas directamente a **Mealie**.

## Características

- **Extracción automática**: obtiene la foto de portada del vídeo, descripción, autor y enlace original desde Instagram, TikTok y YouTube Shorts.
- **PWA e integración móvil ("Compartir con...")**: instalable como aplicación en Android/iOS con soporte Web Share Target para enviar vídeos directamente desde el botón Compartir de las apps sociales.
- **Sustitución de imagen**: permite subir o arrastrar una foto alternativa si la portada del vídeo no te convence.
- **Parseo inteligente**: detecta secciones de ingredientes, cantidades numéricas, unidades y notas.
- **Asistente de revisión de dudas**: cruza ingredientes con los alimentos existentes en Mealie y pregunta si hay dudas o alimentos parecidos para evitar duplicados.
- **Editor en vivo**: permite modificar o añadir ingredientes, pasos, raciones, categorías y tiempos de cocción antes de guardar.
- **Historial reciente**: listado de las últimas recetas importadas con enlaces directos a Mealie.
- **Integración con Mealie**: sube la receta completa, asigna tags y categorías, enlaza ingredientes con pasos y sube la imagen de portada.

## Ejecución local (desarrollo)

```bash
cd mealie-importer
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --port 8094 --reload
```

Abre en tu navegador: [http://localhost:8094](http://localhost:8094)

## Acceso

- **URL web**: [http://localhost:8094](http://localhost:8094) (o tu IP local: `http://192.168.5.5:8094`)
- **Mealie**: Conecta por defecto a tu servidor Mealie o mediante el modal de Ajustes ⚙️.

## Despliegue con Docker

El servicio está configurado en `docker/mealie-importer/config.sh` listo para el orquestador `./update.sh`.

```bash
cd ../docker
./update.sh mealie-importer
```
