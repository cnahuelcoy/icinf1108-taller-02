# CRUD Students & Pets (FastAPI)

Proyecto FastAPI que implementa un **CRUD** para la entidad `Student` y sus `Pet`, con **almacenamiento en memoria** a través de repositorios respaldados por diccionarios. Los datos viven mientras el proceso esté corriendo.

## Tecnologías

- Python 3.13
- FastAPI + repositorios en memoria
- HTML + JS + Tailwind CSS (frontend estático)
- Docker Compose: PostgreSQL 17 y pgAdmin 4 (ver [Docker y PostgreSQL](#docker-y-postgresql))

## Resumen funcional

La API expone operaciones CRUD completas sobre estudiantes y mascotas:

**Estudiantes** — `/api/students`

- **Crear**: `POST /api/students` (opcionalmente con `pets[]` para crear el estudiante y sus mascotas en una sola petición)
- **Listar**: `GET /api/students`
- **Buscar por id**: `GET /api/students/:id`
- **Actualizar**: `PATCH /api/students/:id`
- **Eliminar**: `DELETE /api/students/:id` (elimina también sus mascotas)

**Mascotas** — `/api/students/:studentId/pets`

- **Listar**: `GET /api/students/:studentId/pets`
- **Crear**: `POST /api/students/:studentId/pets`
- **Actualizar**: `PATCH /api/students/:studentId/pets/:petId`
- **Eliminar**: `DELETE /api/students/:studentId/pets/:petId`

### Alta de estudiante con mascotas

`POST /api/students` acepta un arreglo opcional `pets`:

```json
{
	"name": "Ana Pérez",
	"username": "ana_perez",
	"email": "ana@example.com",
	"age": 21,
	"pets": [
		{ "name": "Firulais", "species": "perro", "age": 3 },
		{ "name": "Michi", "species": "gato" }
	]
}
```

Si no se envía `pets` (o se envía vacío), el comportamiento es exactamente el mismo de antes.

> **Punto de transacción:** este endpoint realiza varias escrituras (el estudiante y cada mascota). Con un ORM/SQL, todas deben ejecutarse dentro de una transacción: si una mascota falla (por ejemplo, por nombre duplicado), el estudiante y las mascotas anteriores no deben quedar guardados. En esta versión en memoria la implementación es secuencial y **no** hace rollback, a propósito, para que la actividad de ORM/transacciones parta de ese problema.

### Modelo de datos

| Estudiante | Mascota        |
| ---------- | -------------- |
| id (UUID)  | id (UUID)      |
| name       | studentId      |
| username   | name           |
| email      | species        |
| age        | age (opcional) |
| createdAt  | createdAt      |
| updatedAt  | updatedAt      |

### Validación y unicidad

La validación se realiza con Pydantic v2:

- `name` (estudiante): texto de 3 a 100 caracteres, sin etiquetas HTML.
- `username`: texto de 3 a 30 caracteres, solo minúsculas, números y guiones bajos (`^[a-z0-9_]+$`).
- `email`: dirección de correo electrónico válida.
- `age` (estudiante): entero entre 18 y 99.
- `name` / `species` (mascota): texto de 1 a 50 caracteres, sin etiquetas HTML.
- `age` (mascota): entero entre 0 y 100 (opcional).

Unicidad (rechazado con `409 Conflict`):

- Estudiante: `email` y `username` deben ser únicos.
- Mascota: `name` debe ser único dentro de un mismo estudiante.

## Estándar de respuesta JSON

Toda respuesta de la API — exitosa o de error — usa el mismo **envelope** `ApiResponse`, definido en [`app/shared/api_response.py`](app/shared/api_response.py). Esto permite que el frontend interprete cualquier respuesta de forma uniforme.

### Envelope común

| Campo       | Tipo                | Descripción                                                               |
| ----------- | ------------------- | ------------------------------------------------------------------------- |
| `code`      | `number`            | Código de estado HTTP (coincide con el status de la respuesta).           |
| `success`   | `boolean`           | `true` si la operación se completó, `false` si hubo error.                |
| `message`   | `string`            | Resumen legible del resultado (varía según el método HTTP).               |
| `timestamp` | `string`            | Fecha/hora en ISO 8601 de la respuesta.                                   |
| `data`      | `object \| null`    | Datos de la operación. Presente en éxito; `null` en errores.              |
| `error`     | `string` (opcional) | Mensaje de error para errores simples (404, 500).                         |
| `errors`    | `object` (opcional) | Errores por campo para validación (400) y conflicto (409). Ver más abajo. |

### Respuestas de éxito

Un middleware global ([`api_response.py`](app/shared/api_response.py)) envuelve el retorno de los controladores en `data`:

- **Recurso único** (`GET :id`, `POST`, `PATCH`, `DELETE`): `data` contiene la entidad directamente.
- **Listado** (`GET` colección): `data` contiene `{ total, items }`.

```json
{
  "code": 201,
  "success": true,
  "message": "Recurso creado",
  "timestamp": "2026-09-09T16:49:33.368Z",
  "data": {
    "id": "c3600646-abe8-4be3-8096-d6ad629388e2",
    "name": "Juan Pérez",
    "username": "juanperez",
    "email": "juan@example.com",
    "age": 20,
    "createdAt": "2026-09-09T16:49:33.000Z",
    "updatedAt": "2026-09-09T16:49:33.000Z"
  }
}
```

`message` según el método HTTP:

| Método   | `message`             | `code` |
| -------- | --------------------- | ------ |
| `GET`    | `Operación exitosa`   | 200    |
| `POST`   | `Recurso creado`      | 201    |
| `PATCH`  | `Recurso actualizado` | 200    |
| `DELETE` | `Recurso eliminado`   | 200    |

### Errores simples (404, 500)

Los errores sin detalle por campo usan el campo `error`:

```json
{
  "code": 404,
  "success": false,
  "message": "Estudiante no encontrado",
  "timestamp": "2026-09-09T16:49:53.816Z",
  "data": null,
  "error": "Estudiante no encontrado"
}
```

### Validación (400) y conflicto (409)

Ambos casos comparten el **mismo esquema** para que el frontend los trate igual: el campo `errors` es un mapa `{ campo: { message } }`, donde la clave es el nombre del campo que falla.

```json
{
  "code": 400,
  "success": false,
  "message": "Error de validación",
  "timestamp": "2026-09-09T16:39:30.397Z",
  "data": null,
  "errors": {
    "name": { "message": "El nombre debe tener entre 3 y 100 caracteres" },
    "email": { "message": "El correo electrónico no es válido" }
  }
}
```

```json
{
  "code": 409,
  "success": false,
  "message": "Conflicto con datos existentes",
  "timestamp": "2026-09-09T16:49:45.110Z",
  "data": null,
  "errors": {
    "email": { "message": "El correo electrónico ya está en uso" }
  }
}
```

- `400 Bad Request`: cuando falla la validación. Los DTOs replican las reglas y mensajes de class-validator (NestJS) en español; el handler global ([`exceptions.py`](app/shared/exceptions.py)) convierte los errores al mapa `{ campo: { message } }` (si un campo falla varias reglas, los mensajes se concatenan con `", "`; las propiedades no permitidas devuelven `errors: {}`).
- `409 Conflict`: cuando se viola una restricción de unicidad. Los servicios lanzan una `HTTPException` con el mismo mapa `errors`, por lo que es indistinguible de una validación a nivel de estructura.

### Interpretación en el frontend

El cliente estático (`public/`) consume este estándar de forma uniforme:

- `public/js/api.js` expone `api()` (hace `fetch` y devuelve `data` en éxito o lanza el envelope en error) y `normalizeErrors()` (convierte `{ campo: { message } }` en `{ campo: message }`).
- En los formularios, si la respuesta trae `errors`, cada mensaje se muestra bajo su input correspondiente; si trae `error`, se muestra como notificación global (toast).

## Contexto técnico

- **Backend**: FastAPI
- **Persistencia**: en memoria (repositorios respaldados por diccionarios); los datos se pierden al reiniciar. PostgreSQL ya se ejecuta en Docker y la migración de los repositorios se realiza en las siguientes etapas del taller
- **Validación**: Pydantic v2
- **Frontend**: archivos estáticos en `public/` (Alpine.js + Tailwind CSS + vanilla-sonner, vía CDN)
- **Gestor de dependencias**: uv
- **Documentación**: Swagger en `/docs`

## Ejecución local

1. Instalar dependencias:

    ```bash
    make install
    ```

    O directamente con uv:

    ```bash
    uv sync
    ```

2. Levantar el servidor en modo desarrollo:

    ```bash
    make dev
    ```

    O usando uv:

    ```bash
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 3000
    ```

La aplicación queda disponible en:

- `http://localhost:3000`
- `http://localhost:3000/docs`

> Al ser un almacenamiento en memoria, los datos se pierden cada vez que se reinicia el servidor (incluido el reload de desarrollo).

## Docker y PostgreSQL

Esta sección corresponde a la **Parte 1 del Taller Evaluado II**: levantar PostgreSQL y pgAdmin con Docker Compose, configurar las credenciales mediante variables de entorno y comprobar que los datos se conservan.

### Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y en ejecución (incluye Docker Compose v2).
- PowerShell (Windows PowerShell 5.1 o PowerShell 7) para el script de verificación.
- Los comandos se ejecutan desde la **raíz del repositorio** (donde está `compose.yml`).

### Servicios

| Servicio  | Imagen                | Puerto interno | Puerto en el equipo     | Uso                                  |
| --------- | --------------------- | -------------- | ----------------------- | ------------------------------------ |
| `db`      | `postgres:17-alpine`  | `5432`         | `POSTGRES_PORT` (5432)  | Base de datos `students_pets`        |
| `pgadmin` | `dpage/pgadmin4:9.18` | `80`           | `PGADMIN_PORT` (5050)   | Administración visual de PostgreSQL  |
| `api`     | `Dockerfile` propio   | `3000`         | `API_PORT` (3000)       | FastAPI (definido en `compose.api.yml`) |

- Todos los servicios se comunican por la red `backend_net`. Dentro de esa red, PostgreSQL se alcanza con el nombre de host **`db`** y el puerto **`5432`**.
- Los datos se guardan en los volúmenes con nombre `postgres_data` y `pgadmin_data`, por lo que sobreviven a la detención y eliminación de los contenedores.
- Los puertos de `db` y `pgadmin` se publican solo en `127.0.0.1`, es decir, solo son accesibles desde tu propio equipo.

### 1. Configurar las variables de entorno

Las credenciales **no se escriben en `compose.yml`**: Docker Compose las lee desde un archivo `.env` en la raíz del proyecto. El repositorio incluye una plantilla, `.env.example`, con valores de ejemplo y contraseñas ficticias.

1. Copia la plantilla (PowerShell, desde la raíz del repositorio):

    ```powershell
    Copy-Item .env.example .env
    ```

    En Git Bash, macOS o Linux: `cp .env.example .env`

2. Abre `.env` en VS Code (`code .env`) y reemplaza al menos `POSTGRES_PASSWORD` y `PGADMIN_DEFAULT_PASSWORD` por contraseñas propias.

3. Actualiza `DATABASE_URL` para que use **la misma** contraseña, usuario, puerto y base de datos que definiste arriba.

Variables requeridas:

| Variable                   | Ejemplo                                                                  | Descripción                                                  |
| -------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------ |
| `POSTGRES_DB`              | `students_pets`                                                          | Base de datos creada al iniciar `db` por primera vez         |
| `POSTGRES_USER`            | `students_admin`                                                         | Usuario de PostgreSQL                                        |
| `POSTGRES_PASSWORD`        | `cambia_esta_clave_postgres`                                             | Contraseña de PostgreSQL (**cámbiala**)                      |
| `POSTGRES_PORT`            | `5432`                                                                   | Puerto del equipo publicado hacia el `5432` interno          |
| `PGADMIN_DEFAULT_EMAIL`    | `admin@example.com`                                                      | Correo para iniciar sesión en pgAdmin                        |
| `PGADMIN_DEFAULT_PASSWORD` | `cambia_esta_clave_pgadmin`                                              | Contraseña de pgAdmin (**cámbiala**)                         |
| `PGADMIN_PORT`             | `5050`                                                                   | Puerto del equipo para abrir pgAdmin                         |
| `DATABASE_URL`             | `postgresql+psycopg://students_admin:...@localhost:5432/students_pets`   | URL de conexión que usa SQLAlchemy                           |
| `API_PORT`                 | `3000`                                                                   | Puerto del equipo publicado hacia el `3000` interno de FastAPI |

Sobre `DATABASE_URL`:

- Formato: `postgresql+psycopg://USUARIO:CONTRASEÑA@HOST:PUERTO/BASE_DE_DATOS`.
- Si la API se ejecuta **en tu equipo** (`uv run ...`): host `localhost` y puerto `POSTGRES_PORT`.
- Si la API se ejecuta **dentro de Docker**: host `db` y puerto `5432` (el puerto interno, no el publicado).
- Si la contraseña contiene caracteres especiales (`@ : / # ? %`), deben codificarse en la URL (por ejemplo `@` → `%40`). Lo más simple es usar contraseñas con letras, números y guiones bajos.

> **Importante:** `POSTGRES_USER`, `POSTGRES_PASSWORD` y `POSTGRES_DB` solo se aplican la **primera vez** que se crea el volumen `postgres_data`. Si cambias la contraseña después, PostgreSQL seguirá usando la anterior. Para empezar de cero (borrando los datos) ejecuta `docker compose down -v` y vuelve a iniciar.

### 2. Mantener las credenciales fuera del repositorio

- `.env` está incluido en `.gitignore` y en `.dockerignore`, así que Git no lo versiona y no se copia dentro de la imagen de la API.
- **Nunca** ejecutes `git add -f .env` ni pegues contraseñas reales en `.env.example`, en `compose.yml`, en el código ni en issues o Pull Requests.
- Cada integrante mantiene su propio `.env` local. Las contraseñas se comparten, si es necesario, por un canal privado, no por el repositorio.
- Antes de cada commit revisa qué vas a subir:

    ```powershell
    git status
    git check-ignore -v .env   # debe mostrar la regla de .gitignore que lo ignora
    git ls-files .env          # no debe mostrar nada
    ```

- Si `.env` llegara a versionarse por error: `git rm --cached .env`, haz commit y **cambia las contraseñas**, ya que quedan en el historial.

### 3. Iniciar los contenedores

```powershell
docker compose up -d
```

- `-d` ejecuta los contenedores en segundo plano.
- La primera vez se descargan las imágenes, por lo que puede tardar unos minutos.
- `pgadmin` espera a que `db` esté **healthy** (comprobado con `pg_isready`) antes de iniciar.

Comprobar el estado:

```powershell
docker compose ps            # db debe aparecer como "running (healthy)"
docker compose logs db       # registros de PostgreSQL
docker compose logs -f pgadmin   # registros de pgAdmin en vivo (Ctrl + C para salir)
```

Para levantar también la API dentro de Docker se combinan ambos archivos (`compose.api.yml` define el servicio `api`, que espera a que `db` esté healthy y recibe su propia `DATABASE_URL` con host `db`):

```powershell
docker compose -f compose.yml -f compose.api.yml up -d --build
```

### 4. Detener los contenedores

| Comando                  | Qué hace                                                                 | ¿Se conservan los datos? |
| ------------------------ | ------------------------------------------------------------------------ | ------------------------ |
| `docker compose stop`    | Detiene los contenedores sin eliminarlos                                 | Sí                       |
| `docker compose start`   | Vuelve a iniciar contenedores detenidos con `stop`                       | Sí                       |
| `docker compose down`    | Detiene y elimina contenedores y la red                                  | Sí (quedan los volúmenes) |
| `docker compose down -v` | Además elimina los volúmenes `postgres_data` y `pgadmin_data`            | **No, borra todo**       |

> Usa `docker compose down -v` solo cuando quieras reiniciar la base de datos desde cero.

### 5. Acceder a pgAdmin y registrar el servidor

1. Abre `http://localhost:5050` (o el puerto definido en `PGADMIN_PORT`). La primera carga puede tardar hasta un minuto.
2. Inicia sesión con `PGADMIN_DEFAULT_EMAIL` y `PGADMIN_DEFAULT_PASSWORD` de tu `.env`.
3. En el panel izquierdo, clic derecho sobre **Servers** → **Register** → **Server...**
4. Pestaña **General**:
    - **Name**: `students_pets (Docker)` (nombre descriptivo, solo se usa en pgAdmin).
5. Pestaña **Connection**:
    - **Host name/address**: `db`
    - **Port**: `5432`
    - **Maintenance database**: `students_pets`
    - **Username**: el valor de `POSTGRES_USER`
    - **Password**: el valor de `POSTGRES_PASSWORD`
    - **Save password?**: opcional (se guarda en el volumen local `pgadmin_data`, no en el repositorio).
6. Clic en **Save**. Al expandir el servidor deberías ver **Databases → students_pets**.

> **¿Por qué `db` y no `localhost`?** pgAdmin se ejecuta dentro de un contenedor. Para él, `localhost` es su propio contenedor; PostgreSQL se encuentra en la red `backend_net` con el nombre del servicio, `db`, y el puerto interno `5432`. En cambio, desde tu equipo (por ejemplo DBeaver o la API ejecutada con `uv`) se usa `localhost` y `POSTGRES_PORT`.

### 6. Verificar la configuración con el script

El script `scripts/verify_docker.ps1` solo **lee** información (no modifica archivos ni contenedores) y nunca muestra contraseñas. Revisa:

- que Docker y Docker Compose estén instalados y en ejecución;
- que existan `.env.example` y `.env`, con las 9 variables requeridas y sin contraseñas de ejemplo;
- que `.env` esté ignorado por Git y no esté versionado;
- que `DATABASE_URL` sea coherente con usuario, contraseña, puerto y base de datos;
- que `compose.yml` sea válido y defina `db`, `pgadmin` y la red `backend_net`;
- el estado de los contenedores, la red, el volumen, la conexión a `students_pets` y la respuesta de pgAdmin.

```powershell
# Revisión completa (con los contenedores iniciados)
.\scripts\verify_docker.ps1

# Solo configuración, sin revisar contenedores
.\scripts\verify_docker.ps1 -SkipServices

# Incluir la comprobación de la API en http://localhost:API_PORT/docs
.\scripts\verify_docker.ps1 -CheckApi
```

Si Windows bloquea la ejecución de scripts, ejecútalo así (solo afecta a esa ejecución):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_docker.ps1
```

El script termina con un resumen de correctos, avisos y errores, y devuelve código de salida `1` si encontró errores.

### 7. Verificar que los datos persisten

Esta prueba crea una tabla temporal, detiene y elimina los contenedores, y comprueba que el dato sigue ahí al volver a iniciarlos.

1. Con los contenedores iniciados, abre una consola `psql` dentro del contenedor (reemplaza el usuario si cambiaste `POSTGRES_USER`):

    ```powershell
    docker compose exec db psql -U students_admin -d students_pets
    ```

2. Dentro de `psql`, crea una tabla de prueba e inserta un registro:

    ```sql
    CREATE TABLE IF NOT EXISTS persistence_check (
        id SERIAL PRIMARY KEY,
        note TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    INSERT INTO persistence_check (note) VALUES ('dato antes de reiniciar');
    SELECT * FROM persistence_check;
    \q
    ```

3. Detén y elimina los contenedores **sin** `-v`:

    ```powershell
    docker compose down
    docker compose ps          # no debe listar contenedores
    docker volume ls           # el volumen *_postgres_data debe seguir existiendo
    ```

4. Vuelve a iniciarlos y espera a que `db` esté healthy:

    ```powershell
    docker compose up -d
    docker compose ps
    ```

5. Consulta nuevamente:

    ```powershell
    docker compose exec db psql -U students_admin -d students_pets -c "SELECT * FROM persistence_check;"
    ```

    Si aparece la fila `dato antes de reiniciar` con su `created_at` original, los datos persisten gracias al volumen `postgres_data`.

6. Opcional: elimina la tabla de prueba.

    ```powershell
    docker compose exec db psql -U students_admin -d students_pets -c "DROP TABLE persistence_check;"
    ```

La misma prueba puede hacerse desde pgAdmin con **Tools → Query Tool**. También puedes comprobar que el servidor registrado en pgAdmin sigue apareciendo después del reinicio, ya que su configuración se guarda en el volumen `pgadmin_data`.

### 8. Probar la conexión desde Python

Con `db` iniciado y `DATABASE_URL` apuntando a `localhost`, el módulo `app/database/check_connection.py` ejecuta `SELECT 1` contra PostgreSQL:

```powershell
uv sync
uv run python -m app.database.check_connection
```

### Solución de problemas

- **`docker` no responde / `error during connect`**: Docker Desktop no está iniciado.
- **`port is already allocated`**: el puerto ya está en uso (por ejemplo, un PostgreSQL instalado en Windows en el `5432`). Cambia `POSTGRES_PORT` o `PGADMIN_PORT` en `.env` (por ejemplo `5433`), actualiza `DATABASE_URL` y vuelve a ejecutar `docker compose up -d`.
- **`POSTGRES_PASSWORD requerido`** u otro mensaje similar: falta `.env` o la variable está vacía.
- **`password authentication failed`**: la contraseña de `.env` no coincide con la que se usó al crear el volumen. Usa la contraseña original o reinicia con `docker compose down -v` (borra los datos).
- **pgAdmin no conecta al servidor**: revisa que el host sea `db` y el puerto `5432`, no `localhost`.
- **pgAdmin no inicia y el log menciona el correo**: `PGADMIN_DEFAULT_EMAIL` debe ser un correo con formato válido (por ejemplo `admin@example.com`).

## Comandos útiles

- `make install` — sincroniza dependencias con uv
- `make dev` — arranca uvicorn en modo reload
- `make lint` — ejecuta Ruff (con autocorrección)
- `make format` — formatea el código con Ruff
- `make format-check` — verifica el formato
- `make clean` — elimina `.venv`, cachés y artefactos
- `docker compose up -d` / `docker compose down` — inicia / detiene PostgreSQL y pgAdmin
- `.\scripts\verify_docker.ps1` — comprueba la configuración y el estado de los servicios Docker