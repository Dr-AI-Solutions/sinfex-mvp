========================================================================
ASISTENTE DE LABORATORIO CLÍNICO - GUÍA PARA INFORMÁTICA (TI)
========================================================================

1. DESCRIPCIÓN GENERAL (100% OFFLINE, DETERMINISTA Y SIN IA)
--------------------------------------------------------------
Aplicación web 100% estática (HTML, CSS, JavaScript puro + JSON).
- Sin backend, sin base de datos, sin APIs de IA y sin consumo de
  CPU/RAM en el servidor del hospital.
- Toda la búsqueda difusa se ejecuta en memoria en el navegador del
  usuario (PC de box médico o celular) utilizando Fuse.js.
- Funciona tanto en servidor web (HTTP/HTTPS) como abriendo `index.html`
  directamente con doble clic (`file://`) gracias a `datos_examenes.js`.

2. DESPLIEGUE EN SERVIDOR DEL HOSPITAL
--------------------------------------
1. Copiar el contenido completo de esta carpeta `web/` en el directorio
   público de cualquier servidor web (IIS, Apache, Nginx, etc.), por
   ejemplo: `https://intranet.hospital.cl/asistente-lab/`
2. Verificar que el servidor sirva archivos `.json` con MIME type
   `application/json`.
3. Nota sobre red interna sin salida a Internet:
   - Actualmente `index.html` carga Fuse.js desde CDN (`cdn.jsdelivr.net`)
     y `admin.html` carga `pdf.js` desde `cdnjs.cloudflare.com`.
   - Si los boxes médicos no tienen acceso a Internet, descargue `fuse.min.js`
     (y `pdf.min.js` / `pdf.worker.min.js` para `admin.html`) en `web/` y
     cambie las etiquetas `<script>` a rutas locales.

3. ACTUALIZACIÓN DE PROTOCOLOS SIN PROGRAMAR (`web/admin.html`)
---------------------------------------------------------------
Cuando el laboratorio publique PDFs nuevos o actualizados en SINFEX:
1. Abra `web/admin.html` en su navegador (o haga clic en "Actualizar PDFs").
2. Cargue el archivo `base_examenes.json` actual.
3. Arrastre uno o varios PDFs nuevos/actualizados de SINFEX.
   El panel extrae los campos localmente en el navegador usando la
   plantilla fija de SINFEX (sin IA ni envío de archivos a terceros).
4. Haga clic en "Aplicar a la base" (actualiza o inserta por `codigo_interno`).
5. Descargue `base_examenes.json` y `datos_examenes.js`, y reemplácelos
   en la carpeta `web/` del servidor.

4. INTEGRACIÓN FUTURA CON API INTERNA (OPCIONAL)
------------------------------------------------
Si en el futuro desean servir los exámenes desde una API REST interna:
1. Abrir `web/app.js`.
2. Modificar la constante `DATA_SOURCE_URL` al inicio del archivo con
   la URL del endpoint interno (debe retornar el mismo esquema JSON).

5. PRUEBA LOCAL RÁPIDA
----------------------
- Opción A (sin servidor): Abrir `web/index.html` con doble clic.
- Opción B (servidor local): Ejecutar dentro de `web/`:
    python -m http.server 8080
  Luego abrir: http://localhost:8080
========================================================================
