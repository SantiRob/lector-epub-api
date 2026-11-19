# Lector EPUB API

Backend FastAPI para un lector Android. La app consulta el catálogo, descarga EPUB y publica reseñas pendientes al recuperar conexión. Progreso y marcadores quedan en el dispositivo en v1.

## Arquitectura

- app/api: HTTP, esquemas y HTTP Basic.
- app/services: casos de uso, validación e idempotencia.
- app/repositories: consultas PostgreSQL.
- app/infrastructure: conexión y almacenamiento.
- app/models.py: ORM; alembic/: migración; tests/: integración.

PostgreSQL guarda metadatos y reseñas. EPUB y portadas viven en un volumen persistente; no se descargan libros automáticamente.

## Configuración y arranque

Requiere Docker con el motor en funcionamiento. Copie .env.example a .env y complete POSTGRES_PASSWORD, ADMIN_USERNAME, ADMIN_PASSWORD y DATABASE_URL. La contraseña en DATABASE_URL debe coincidir con POSTGRES_PASSWORD y codificarse como parte de una URL si tiene caracteres especiales. La forma es postgresql+psycopg://epub:PASSWORD_URL_ENCODED@db:5432/epub. .env está excluido de Git y de la imagen.

    Copy-Item .env.example .env
    # Edite .env antes de continuar.
    docker compose build
    docker compose up -d
    docker compose ps
    docker compose logs -f api
    curl.exe http://localhost:8000/api/v1/health

La API se publica solo en 127.0.0.1:8000. /docs y /openapi.json muestran el contrato. Compose espera el healthcheck de PostgreSQL; la API ejecuta alembic upgrade head antes de iniciar. Para migrar manualmente: docker compose run --rm api alembic upgrade head. La imagen local se llama epub-api:v1.

Reconstruya con docker compose build y docker compose up -d --force-recreate. Los volúmenes postgres_data y uploads_data conservan libros y reseñas. docker compose down detiene sin borrar datos; down -v borra los volúmenes. Revise fallos con docker compose logs --tail=200 api db.

Para acceso remoto, termine TLS en un proxy HTTPS y configure CORS_ORIGINS como arreglo JSON de orígenes permitidos, por ejemplo ["https://lector.ejemplo.com"]. HTTP Basic requiere HTTPS fuera de localhost. No hay cuentas de lector, tokens ni tabla de usuarios.

## Carga desde Postman

Suba solo libros cuya distribución esté permitida y registre fuente/autorización en rights_note. Importe [postman_collection.json](postman_collection.json) o cree POST http://localhost:8000/api/v1/books. En Authorization seleccione Basic Auth y use ADMIN_USERNAME y ADMIN_PASSWORD de .env. En Body seleccione form-data: title, author, language (es/en), rights_note, description y source_url opcionales, epub como File y cover opcional como File. Deje que Postman establezca Content-Type multipart.

    curl.exe -u "<usuario>:<contraseña>" -F "title=Libro permitido" -F "author=Autora" -F "language=es" -F "rights_note=Fuente y permiso" -F "epub=@C:\ruta\libro.epub" http://localhost:8000/api/v1/books
    curl.exe "http://localhost:8000/api/v1/books?q=Libro&language=es&limit=20"
    curl.exe -o libro.epub "http://localhost:8000/api/v1/books/1/download"

Para publicar reseña, envíe POST /api/v1/books/1/reviews con JSON:

    {"client_review_id":"d95b8ef5-4c56-4dd6-9acc-24969b8ca46f","display_name":"Lector","rating":5,"comment":"Me gustó"}

## Contrato

Todas las rutas usan /api/v1. GET /health informa el estado básico. GET /books devuelve libros publicados, admite q (título o autor), language, cursor de ID exclusivo y limit 1–50 (20 predeterminado). Cada libro incluye promedio y cantidad de reseñas, has_cover y URLs relativas de portada y descarga, sin rutas internas. GET /books/{id} ofrece la ficha; /cover entrega JPG/PNG/WebP y /download application/epub+zip. POST /books requiere HTTP Basic, limita EPUB a 25 MiB y portada a 5 MiB, valida contenido y devuelve 409 ante SHA-256 duplicado. GET /books/{id}/reviews pagina por ID; POST /books/{id}/reviews devuelve 201 al crear, 200 para un reintento idéntico y 409 si el UUID ya identifica datos distintos. No hay edición ni eliminación en v1.

Android genera client_review_id UUID al guardar una reseña pendiente, y conserva ese UUID en los reintentos. Tras 201 o 200 puede marcarla sincronizada; 409 requiere resolver el conflicto local; 422 requiere corregir los datos. El nombre visible no verifica identidad. Las reseñas anónimas pueden recibir contenido no deseado; no hay moderación ni límite por persona en v1.

## Pruebas y persistencia

Las pruebas requieren un PostgreSQL de prueba separado. Con Compose, use el archivo de pruebas para publicar PostgreSQL solo en localhost:5433 y cree la base:

    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d
    docker compose exec -T db createdb -U epub test_epub

Defina TEST_DATABASE_URL con postgresql+psycopg://epub:PASSWORD_URL_ENCODED@127.0.0.1:5433/test_epub (codifique caracteres especiales), instale requirements-dev.txt y ejecute python -m pytest -q. El fixture exige un nombre con test, aplica Alembic y trunca solo esa base entre pruebas. Las pruebas cubren búsqueda, filtro, cursor, ficha, portada, descarga, autenticación, límites de cuerpo, archivos inválidos/grandes/duplicados y reseñas.

Para verificar persistencia, cargue un libro y reseña, anote sus IDs, reconstruya con docker compose build y docker compose up -d --force-recreate, y vuelva a consultar /books/{id} y /books/{id}/reviews. El script scripts/smoke_compose.py hace esta comprobación en dos pasos (create antes y verify después); requiere ADMIN_USERNAME y ADMIN_PASSWORD en el entorno y httpx instalado. La validación EPUB limita entradas, tamaño descomprimido, proporción de compresión, rutas peligrosas y archivos de lectura. No sustituye un análisis antimalware; cargue fuentes confiables.
