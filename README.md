# Serena Backend 🧠

> Backend API para el sistema de análisis biométrico emocional de un centro de psicoterapia.
> Construido con **FastAPI**, **SQLAlchemy 2.0 (async)**, **Alembic**, **Celery**, **Redis** y **Docker**.

---

## Tabla de Contenidos

- [Arquitectura](#arquitectura)
- [Requisitos Previos](#requisitos-previos)
- [Configuración Inicial](#configuración-inicial)
- [Levantar el Proyecto (Docker)](#levantar-el-proyecto-docker)
- [Migraciones (Alembic)](#migraciones-alembic)
- [Seeders](#seeders)
- [Documentación API](#documentación-api)
- [Tests](#tests)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Usuarios de Prueba](#usuarios-de-prueba)

---

## Arquitectura

```
Cliente (Frontend / WebSocket)
          │
          ▼
    FastAPI (Puerto 8000)
          │
    ┌─────┴─────┐
    │  API v1   │  ← /api/v1/auth, /users, /patients, /sessions, /biometric, /reports, /alerts
    └─────┬─────┘
          │
    ┌─────┴──────┐
    │  Services  │  ← Lógica de negocio, evaluación de alertas
    └─────┬──────┘
          │
    ┌─────┴────────────┐
    │  Repositories    │  ← Acceso a datos (SQLAlchemy async)
    └─────┬────────────┘
          │
    ┌─────┴──────┐        ┌──────────────┐
    │ PostgreSQL │        │  Cloudinary  │  ← Videos e imágenes
    └────────────┘        └──────────────┘

    ┌──────────┐    ┌──────────────┐
    │  Redis   │───▶│ Celery Worker│  ← Análisis post-sesión (background)
    └──────────┘    └──────────────┘
```

Cada módulo de negocio sigue el patrón: **Router → Service → Repository → Model**

---

## Requisitos Previos

- Docker + Docker Compose
- PostgreSQL corriendo en Docker con la base de datos `serena_db` ya creada
- Cuenta en [Cloudinary](https://cloudinary.com) para el almacenamiento de videos

---

## 🚀 Levantar el Proyecto

### Paso 1 — Configurar `.env`

Edita el archivo `.env` con tus valores reales:

```bash
# La base de datos ya apunta al contenedor de PostgreSQL en Docker
DATABASE_URL=postgresql+asyncpg://postgres:123@host.docker.internal:5432/serena_db
SYNC_DATABASE_URL=postgresql+psycopg2://postgres:123@host.docker.internal:5432/serena_db

# Genera una clave segura:
# python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=tu-clave-secreta-aqui

# Credenciales de tu cuenta Cloudinary:
CLOUDINARY_CLOUD_NAME=tu-cloud-name
CLOUDINARY_API_KEY=tu-api-key
CLOUDINARY_API_SECRET=tu-api-secret
```

### Paso 2 — Construir y levantar los servicios

```bash
docker compose up --build -d
```

Esto levanta 3 servicios:

| Servicio | Puerto | Descripción |
|---|---|---|
| `serena_api` | 8000 | FastAPI REST + WebSocket |
| `celery_worker` | — | Análisis post-sesión en background |
| `redis` | 6379 | Broker de Celery |

### Paso 3 — Migraciones y seeders (solo la primera vez)

```bash
# Crear y aplicar el esquema de base de datos
docker compose exec serena_api python -m alembic revision --autogenerate -m "initial_schema"
docker compose exec serena_api python -m alembic upgrade head

# Poblar con datos de ejemplo
docker compose exec serena_api python -m app.seeders.run_seeders
```

✅ Listo. Abre **http://localhost:8000/docs** para ver el Swagger completo.

Los seeders son **idempotentes**: no duplican datos si se ejecutan más de una vez.

---

## Documentación API

Una vez levantado el proyecto:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

---

## Tests

```bash
# Instalar dependencias de test (local)
pip install -r requirements.txt

# Ejecutar tests
pytest tests/ -v

# Con cobertura
pytest tests/ --cov=app --cov-report=term-missing

# Dentro de Docker
docker compose exec serena_api pytest tests/ -v
```

---

## Estructura del Proyecto

```
serena_back/
├── app/
│   ├── main.py                    # Entry point FastAPI
│   ├── core/                      # Configuración, DB, seguridad, logging
│   ├── api/v1/router.py           # Agrega todos los módulos bajo /api/v1
│   ├── modules/
│   │   ├── auth/                  # Login, JWT, refresh tokens, audit log
│   │   ├── users/                 # Gestión de usuarios y roles
│   │   ├── patients/              # Expediente clínico digital
│   │   ├── sessions/              # Historial de sesiones + timeline
│   │   ├── biometric/             # Análisis emocional (WebSocket + Celery)
│   │   ├── media/                 # Cloudinary upload/delete
│   │   ├── reports/               # Generador de PDF (WeasyPrint)
│   │   └── alerts/                # Sistema de alertas clínicas
│   ├── workers/celery_app.py      # Configuración Celery
│   └── seeders/                   # Seeders con datos realistas
├── alembic/                       # Migraciones de base de datos
├── tests/                         # Suite de tests (pytest + httpx)
├── Dockerfile                     # Multi-stage build
├── docker-compose.yml             # API + Celery + Redis
├── .env.example                   # Template de variables de entorno
└── requirements.txt
```

---

## Usuarios de Prueba

Después de ejecutar los seeders:

| Rol | Email | Contraseña |
|---|---|---|
| Admin | admin@serena.com | Admin1234! |
| Terapeuta | dra.garcia@serena.com | Terapeuta1! |
| Terapeuta | dr.martinez@serena.com | Terapeuta2! |
| Recepcionista | recepcion@serena.com | Recepcion1! |

---

## Variables de Entorno Clave

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | DSN async PostgreSQL (asyncpg) |
| `SYNC_DATABASE_URL` | DSN sync PostgreSQL (psycopg2, usado por Alembic) |
| `SECRET_KEY` | Clave HMAC para JWT (mínimo 32 chars) |
| `REDIS_URL` | Conexión Redis para Celery |
| `CLOUDINARY_*` | Credenciales Cloudinary para videos/imágenes |

---

## Motor de Análisis Emocional

El servicio biométrico usa un **mock** que genera datos aleatorios realistas.
Para integrarlo con un modelo real, reemplaza la función `_analyze_frame_mock`
en `app/modules/biometric/service.py`:

```python
# Ejemplo con DeepFace:
from deepface import DeepFace

def _analyze_frame_mock(frame_base64: str, timestamp_offset: float) -> dict:
    result = DeepFace.analyze(img_path=decoded_frame, actions=["emotion"])
    # Mapear result[0]["emotion"] al formato esperado
    ...
```

---

*Serena Backend © 2025 — Sistema de análisis biométrico para psicoterapia*
