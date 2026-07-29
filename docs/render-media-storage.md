# MEDIA persistente en Render

Las imágenes subidas no deben guardarse únicamente en el filesystem del Web
Service. El proyecto usa `django-storages` y activa S3/S3-compatible cuando
existe `AWS_STORAGE_BUCKET_NAME`.

Variables de entorno requeridas en Render:

- `AWS_STORAGE_BUCKET_NAME`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_REGION_NAME`

Para un proveedor S3-compatible también configurar:

- `AWS_S3_ENDPOINT_URL`
- `AWS_S3_ADDRESSING_STYLE` (`path` o `virtual`, según el proveedor)

Opcionales:

- `AWS_S3_CUSTOM_DOMAIN`: dominio público/CDN del bucket.
- `AWS_QUERYSTRING_AUTH=1`: URLs firmadas para bucket privado (valor por defecto).
- `AWS_QUERYSTRING_AUTH=0`: solamente si el bucket o CDN permite lectura pública.

`STATIC` continúa servido por WhiteNoise. El storage S3 configurado como
`default` se utiliza exclusivamente para archivos subidos (`MEDIA`).

## Verificación de producción

1. Configurar las variables en Render y desplegar.
2. Editar un traje existente y volver a subir sus fotos.
3. Confirmar que la URL de la imagen apunta al bucket/CDN y responde HTTP 200.
4. Ejecutar **Manual Deploy** y volver a comprobar la misma URL.
5. Reiniciar el Web Service y volver a comprobar la misma URL.
6. Si se usa bucket privado, comprobar la imagen desde la página pública para
   obtener una URL firmada vigente; no reutilizar una URL firmada vencida.
