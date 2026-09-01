# 2.7 — Deployment, Runtime & CI/CD Architecture

**Estado:** FINAL — ajustado tras validación cruzada de Claude  
**Fase:** 2 — Architecture & Engineering Design  
**Sección:** 2.7  
**Proyecto:** Monthly Financial Ledger Automation

---

## 1. Propósito

Definir cómo la aplicación será empaquetada, ejecutada, probada y desplegada en desarrollo y producción, manteniendo:

- aislamiento del backend;
- PostgreSQL como motor de datos;
- separación entre n8n y la lógica financiera;
- despliegues reproducibles;
- mínimo privilegio;
- capacidad de recuperación;
- y gobernanza humana sobre cambios potencialmente destructivos.

Este documento complementa las decisiones de 2.1–2.6. No reemplaza el modelo de datos ni el contrato de API.

---

## 2. Principios heredados

1. **n8n orquesta; Python decide; PostgreSQL persiste.**
2. La lógica financiera no vive en n8n.
3. El backend Python no se expone directamente a Internet.
4. PostgreSQL no se expone directamente a Internet.
5. La aplicación usa una base de datos y un rol propios.
6. El rol de aplicación nunca tendrá `SUPERUSER`, `CREATEDB` ni `CREATEROLE`.
7. Los montos monetarios se manejan con precisión decimal.
8. La idempotencia debe estar respaldada por una restricción `UNIQUE` en PostgreSQL.
9. Las correcciones son append-only / soft-correction.
10. Los datos financieros reales nunca se incorporan al repositorio público.
11. `output/` no se usa como evidencia versionada para datos reales.
12. Las operaciones destructivas requieren aprobación humana explícita.
13. Los agentes de IA pueden asistir al desarrollo, pero no son fuente de verdad del dominio financiero.

---

## 3. Runtime objetivo

La aplicación tendrá un contenedor Docker propio para el backend Python.

Arquitectura conceptual:

```text
Internet
   │
   ▼
Telegram
   │
   ▼
n8n (producción)
   │
   │ HTTP interno
   ▼
monthly-financial-ledger-api
   │
   ▼
PostgreSQL dedicado
```

El backend no necesita un dominio público propio.

---

## 4. Por qué contenedor exclusivo

Se utilizará un contenedor dedicado para el backend porque permite:

- reproducibilidad entre entornos;
- aislamiento de dependencias;
- despliegues controlados;
- rollback de imagen;
- independencia de la instalación Python del VPS;
- menor acoplamiento con n8n;
- portabilidad futura.

No se embebe Python dentro de n8n.

---

## 5. Desarrollo local

El entorno local reproducirá la arquitectura esencial:

```text
Telegram (no requerido)
      │
      ▼
API FastAPI
      │
      ▼
PostgreSQL Docker
```

Telegram y n8n no son necesarios para validar el núcleo financiero.

Se probarán localmente:

- dominio;
- parser;
- API;
- persistencia;
- correcciones;
- idempotencia;
- migraciones;
- generación de reportes/imágenes;
- tests.

La integración real Telegram → n8n → API se validará posteriormente en producción.

---

## 6. PostgreSQL en desarrollo

Se mantiene PostgreSQL como decisión de desarrollo y producción.

No se introduce SQLite.

La razón es mantener el mismo motor relacional entre entornos y evitar divergencias en:

- tipos;
- restricciones;
- transacciones;
- índices;
- comportamiento de concurrencia;
- migraciones.

El PostgreSQL local será independiente del PostgreSQL del VPS.

---

## 7. PostgreSQL en producción

Producción utilizará la instancia PostgreSQL existente:

```text
gonex-postgres
```

dentro del VPS.

El proyecto tendrá:

- base de datos propia;
- esquema propio;
- rol propio;
- credenciales propias.

No utilizará las credenciales administrativas de `gonex`.

---

## 8. Regla de privilegios del rol de aplicación

El rol de PostgreSQL del proyecto deberá cumplir obligatoriamente:

```text
SUPERUSER  = false
CREATEDB   = false
CREATEROLE = false
```

No se copiarán los privilegios del rol administrativo existente.

El rol tendrá únicamente los permisos necesarios para operar sobre la base/esquema del proyecto.

Las tareas administrativas de creación de base, rol o cambios privilegiados serán ejecutadas por un operador autorizado, no por la aplicación.

---

## 9. Redes Docker

### Desarrollo

Se utilizará una red Docker privada del proyecto.

Ejemplo conceptual:

```text
ledger-api
     │
     └── ledger-postgres
```

### Producción

El backend se conectará a PostgreSQL mediante la red Docker apropiada del VPS.

No se asumirá automáticamente que debe unirse a `docker_gonex-network`; esa conexión se configurará explícitamente si es necesaria.

n8n y el backend también tendrán comunicación interna controlada.

---

## 10. No exposición pública del backend

El backend FastAPI no tendrá:

- puerto publicado a Internet;
- dominio público;
- certificado TLS propio;
- acceso directo desde Internet.

La comunicación externa seguirá siendo:

```text
Telegram → n8n
```

y la comunicación con el backend:

```text
n8n → HTTP interno → FastAPI
```

Esto reduce superficie de ataque y evita convertir el backend financiero en un servicio público.

---

## 11. Autenticación n8n → FastAPI

Se utilizará autenticación mediante una API key/secret compartido.

Conceptualmente:

```http
Authorization: Bearer <PROJECT_API_KEY>
```

La clave:

- no estará en Git;
- no estará en `.env` versionado;
- se almacenará como secreto del entorno;
- será conocida únicamente por los componentes que necesitan comunicarse.

El backend rechazará solicitudes sin credencial válida.

La autenticación no sustituye el aislamiento de red: ambas capas son necesarias.

---

## 12. Variables de entorno

Se utilizará `.env.example` para documentar nombres de variables, sin valores reales.

Ejemplo conceptual:

```text
DATABASE_URL=
API_KEY=
TELEGRAM_BOT_TOKEN=
LLM_API_KEY=
```

Los valores reales permanecerán fuera del repositorio.

La conexión PostgreSQL deberá corresponder al usuario y base dedicados del proyecto.

---

## 13. Dependencias Python

El proyecto seguirá el patrón existente de los repos de Erick:

```text
requirements.txt
```

No se introduce `pyproject.toml` como mecanismo principal.

Esta decisión prevalece sobre la propuesta inicial de 2.2 que había sugerido `pyproject.toml`. Se documenta aquí como decisión posterior y fundamentada en el patrón operativo ya utilizado en los proyectos existentes.

---

## 14. Framework

El backend utilizará:

```text
FastAPI
```

en lugar de Flask.

La decisión se justifica por:

- API-first;
- validación estructurada;
- tipado;
- documentación OpenAPI automática;
- integración natural con modelos de request/response;
- buena compatibilidad con servicios HTTP internos.

Flask sigue siendo una tecnología conocida por Erick, pero FastAPI se adopta deliberadamente para este proyecto.

---

## 15. Servidor de aplicación

El contenedor ejecutará FastAPI mediante un servidor ASGI apropiado.

La implementación concreta de workers y parámetros de ejecución se definirá durante la construcción del contenedor y las pruebas de carga básicas.

No se introduce una plataforma de orquestación como Kubernetes.

---

## 16. ORM y migraciones

Se utilizará:

```text
SQLAlchemy
Alembic
```

SQLAlchemy manejará el acceso estructurado a PostgreSQL.

Alembic manejará las migraciones versionadas del esquema.

Esto evita depender de SQL manual arbitrario para evolucionar la base.

---

## 17. Gobernanza de migraciones

Las migraciones serán versionadas en Git.

Regla obligatoria:

> Una migración con potencial destructivo o pérdida de datos requiere aprobación humana explícita antes de aplicarse en producción.

Ejemplos:

- `DROP COLUMN`;
- eliminación de tablas;
- reducción potencialmente destructiva de tipos;
- transformaciones con pérdida de información;
- operaciones equivalentes que puedan hacer irreversible el estado anterior.

Las migraciones aditivas y compatibles podrán formar parte del flujo automatizado de despliegue cuando las pruebas correspondientes hayan pasado.

El pipeline no tendrá permiso para convertir automáticamente una migración destructiva en una acción aprobada.

---

## 18. Compatibilidad de migraciones

Las migraciones deberán diseñarse considerando que:

```text
rollback de código ≠ rollback de esquema
```

Son operaciones independientes.

Un rollback de imagen Docker no garantiza que una versión anterior de la aplicación sea compatible con un esquema ya migrado.

Por tanto:

- el pipeline conservará imágenes anteriores;
- las migraciones tendrán versión;
- antes de hacer rollback de código se deberá considerar el estado actual del esquema;
- los downgrades de Alembic no se ejecutarán automáticamente como consecuencia de un rollback de aplicación;
- la estrategia de compatibilidad entre releases se definirá conforme aparezcan cambios reales de esquema.

No se promete un rollback automático completo de aplicación + base de datos en v1.

---

## 19. Idempotencia

La idempotencia sigue siendo un requisito de integridad.

La secuencia conceptual será:

```text
Request
  │
  ▼
¿Idempotency key ya procesada?
  │
  ├── Sí → devolver resultado existente
  │
  └── No
       │
       ▼
     parser
       │
       ▼
     validación
       │
       ▼
     persistencia
```

La comprobación lógica en Python no será la única defensa.

La base de datos tendrá una restricción `UNIQUE` sobre la clave de idempotencia correspondiente.

Esto garantiza protección frente a condiciones de carrera.

---

## 20. Idempotencia antes del parser/LLM

La deduplicación deberá ocurrir antes de ejecutar parsing costoso.

Esto es especialmente importante porque el flujo puede utilizar:

```text
parser determinístico
        ↓
fallback LLM
```

Un webhook duplicado que ya fue procesado no debe:

- volver a invocar innecesariamente al LLM;
- producir una segunda extracción;
- generar una segunda transacción.

---

## 21. Correcciones

Las correcciones siguen el modelo definido en 2.3.

Una corrección:

- crea un nuevo evento;
- marca el anterior como `SUPERSEDED`;
- se realiza dentro de una transacción PostgreSQL;
- no modifica destructivamente el evento histórico.

Las correcciones pueden encadenarse.

El cálculo operativo considera únicamente registros `ACTIVE`.

---

## 22. Rollback operativo

El rollback de aplicación se realizará mediante una imagen Docker anterior conocida.

Conceptualmente:

```text
Git commit
   ↓
Docker image
   ↓
Deploy
   ↓
Problema
   ↓
Seleccionar imagen anterior
```

El rollback no implica automáticamente:

```text
Alembic downgrade
```

porque eso podría ser más peligroso que el problema original.

Cualquier downgrade de esquema que pueda afectar datos requerirá evaluación y aprobación humana.

---

## 23. CI/CD

Se utilizará:

```text
GitHub
   ↓
GitHub Actions
   ↓
SSH
   ↓
VPS
   ↓
Docker
```

El runner será GitHub-hosted.

No se utilizará un self-hosted runner inicialmente.

---

## 24. Razón para GitHub-hosted runner

Un self-hosted runner tendría acceso directo al entorno del VPS y aumentaría la superficie de ataque.

El runner hospedado por GitHub permite que:

- el código sea construido/testeado fuera del VPS;
- el VPS reciba únicamente el artefacto o despliegue necesario;
- no exista un agente permanente de GitHub Actions dentro de la infraestructura.

---

## 25. Credencial de deployment

La clave SSH utilizada por CI/CD no deberá ser la misma credencial administrativa personal usada para operar manualmente el VPS.

Se recomienda crear un usuario de deployment dedicado, sin `sudo` general, con acceso limitado a:

- directorio de deployment del proyecto;
- operaciones Docker estrictamente necesarias;
- archivos de configuración del proyecto.

La forma exacta de conceder acceso Docker se revisará durante la implementación porque pertenecer al grupo `docker` equivale en la práctica a un nivel de privilegio muy alto sobre el host.

Por ello, esta decisión deberá tratarse como un punto de seguridad de implementación, no como un simple detalle de usuario.

---

## 26. Flujo de deployment

Flujo objetivo:

```text
Developer
   │
   ▼
Feature branch
   │
   ▼
Pull Request / revisión
   │
   ▼
main
   │
   ▼
GitHub Actions
   │
   ├── tests
   ├── lint / checks
   ├── build image
   └── deployment
          │
          ▼
        VPS
          │
          ▼
   Docker container
```

La configuración exacta de branch protection y aprobación de PR se definirá durante la implementación del repositorio.

---

## 27. Regla de cambios destructivos en CI/CD

El pipeline puede automatizar:

- tests;
- build;
- publicación de imagen;
- despliegues compatibles;
- migraciones previamente aprobadas como seguras.

El pipeline no debe interpretar por sí mismo que una operación destructiva es segura.

Toda migración potencialmente destructiva requiere aprobación humana explícita.

Esto aplica aunque el cambio haya sido generado o propuesto por un agente de IA.

---

## 28. Secrets

Nunca se almacenarán en Git:

- API keys;
- tokens de Telegram;
- credenciales PostgreSQL;
- claves LLM;
- claves SSH;
- datos financieros;
- dumps de base de datos.

Los secretos de CI/CD estarán en GitHub Secrets.

Los secretos de producción permanecerán en el entorno del VPS o en el mecanismo de secrets que se adopte posteriormente.

---

## 29. Datos financieros y backups

Los datos reales del ledger no deben aparecer en:

```text
GitHub
logs
fixtures públicos
screenshots públicos
output/
```

Los backups son una excepción operativa necesaria, pero contienen datos financieros reales y por tanto deben considerarse información sensible.

El backup externo en Backblaze B2 deberá:

- utilizar cifrado adecuado en tránsito y reposo;
- restringir el acceso;
- evitar exposición pública;
- conservar únicamente el período necesario según la política operativa.

### Hallazgo de infraestructura existente

Durante la investigación se detectó que el backup existente de GONEX presentaba un problema:

```text
b2: command not found
```

El fallo estaba ocurriendo sin producir una alerta suficiente.

Esto debe considerarse una deuda operativa de infraestructura y no una funcionalidad resuelta por este proyecto.

Además, se detectó que la base `thingsboard` aparece en PostgreSQL pero no está incluida en el array `BASES` del script de backup existente.

Ambos puntos deben quedar registrados como issues de `gonex-infra`, no mezclados con la implementación del ledger.

---

## 30. Desarrollo vs. producción

### Se valida localmente

- FastAPI;
- SQLAlchemy;
- Alembic;
- PostgreSQL;
- parser;
- lógica financiera;
- idempotencia;
- correcciones;
- tests;
- generación de imágenes;
- reportes.

### Se valida en producción

- Telegram;
- webhook;
- n8n;
- comunicación n8n → FastAPI;
- secretos reales;
- Docker networking;
- deployment;
- integración completa.

La validación de producción no reemplaza los tests locales.

---

## 31. Generación de imágenes

Las imágenes de los reportes serán generadas por Python.

n8n no será responsable de:

- dibujar gráficos;
- construir imágenes;
- interpretar datos financieros;
- calcular totales.

n8n únicamente orquestará la entrega del resultado.

---

## 32. GitHub Actions como infraestructura reutilizable

La adopción de GitHub Actions para este proyecto puede convertirse posteriormente en un patrón reutilizable para otros repositorios.

Sin embargo, no se intentará construir desde v1 un framework CI/CD universal para todos los proyectos GONEX.

Primero se implementará un pipeline pequeño y funcional para este proyecto.

Después, los patrones que demuestren utilidad podrán reutilizarse.

---

## 33. Health checks

El contenedor deberá disponer de un mecanismo sencillo para comprobar que la API está viva.

Conceptualmente:

```http
GET /health
```

Debe comprobar como mínimo la disponibilidad básica de la aplicación.

Un endpoint separado de readiness podrá introducirse posteriormente si la necesidad real lo justifica.

---

## 34. Observabilidad mínima

El sistema deberá permitir identificar:

- aplicación iniciada;
- errores HTTP;
- errores de persistencia;
- fallos de integración;
- deployment exitoso o fallido.

No se registrarán:

- montos financieros completos innecesariamente;
- descripciones privadas;
- tokens;
- API keys;
- contraseñas;
- payloads completos de Telegram si contienen información financiera.

---

## 35. Backup y recuperación

El proyecto dependerá del mecanismo de backup PostgreSQL de la infraestructura GONEX, pero no asumirá que dicho backup está sano solo porque exista un script.

Antes de considerar producción confiable se deberá verificar:

1. ejecución real del backup;
2. existencia del archivo generado;
3. subida correcta;
4. retención;
5. posibilidad de restauración.

La restauración será probada al menos una vez antes de considerar el proceso operativo maduro.

---

## 36. Estructura conceptual de deployment

```text
monthly-financial-ledger/
├── app/
├── tests/
├── migrations/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── docs/
```

La estructura exacta podrá cambiar durante la implementación si una necesidad real lo justifica.

---

## 37. Lo que deliberadamente NO se introduce

En v1 no se introduce:

- Kubernetes;
- Docker Swarm;
- Terraform;
- Ansible;
- self-hosted GitHub runner;
- API pública del backend;
- SQLite;
- Redis para el ledger;
- microservicios adicionales;
- service mesh;
- observabilidad compleja;
- framework CI/CD universal;
- rollback automático de base de datos;
- sistema de secretos externo dedicado.

Cada una de estas tecnologías puede ser útil en otros contextos, pero introducirlas ahora aumentaría complejidad sin resolver una necesidad demostrada.

---

## 38. Riesgos operativos conocidos

### R1 — Backup existente defectuoso

El mecanismo actual de backup de GONEX presenta un fallo conocido (`b2: command not found`).

**Tratamiento:** issue de infraestructura y verificación de restauración.

### R2 — Privilegios Docker

El acceso al Docker daemon concede privilegios elevados.

**Tratamiento:** usar un usuario de deployment dedicado y revisar cuidadosamente cómo se concederá acceso Docker.

### R3 — Compatibilidad rollback/esquema

Un rollback de código puede dejar el esquema en una versión incompatible.

**Tratamiento:** no asumir rollback conjunto automático.

### R4 — Secrets

Una mala gestión de secretos podría comprometer el sistema.

**Tratamiento:** GitHub Secrets + secretos únicamente en entornos privados.

---

## 39. Pendientes para implementación

Quedan deliberadamente para la fase de implementación:

1. Dockerfile definitivo.
2. Compose local.
3. Compose/servicio de producción.
4. Creación de base y rol PostgreSQL dedicados.
5. Configuración exacta de red Docker.
6. Usuario de deployment.
7. Restricciones de acceso Docker para deployment.
8. GitHub Actions.
9. Branch protection.
10. Configuración de secrets.
11. Migración inicial Alembic.
12. Health check real.
13. Política concreta de logs.
14. Prueba real de backup/restauración.
15. Política concreta de compatibilidad entre releases.

---

## 40. Decisiones cerradas de 2.7

| Tema | Decisión |
|---|---|
| Runtime | Docker |
| Backend | Contenedor exclusivo |
| Framework | FastAPI |
| DB | PostgreSQL |
| Desarrollo DB | PostgreSQL local |
| Producción DB | `gonex-postgres` |
| ORM | SQLAlchemy |
| Migraciones | Alembic |
| API pública | No |
| n8n → API | HTTP interno |
| Auth interna | API key / Bearer secret |
| CI/CD | GitHub Actions |
| Runner | GitHub-hosted |
| Deployment | SSH |
| Usuario deployment | Dedicado, sin sudo general |
| Idempotencia | `UNIQUE` en PostgreSQL |
| Parsing | Antes de persistencia; deduplicación primero |
| Migraciones destructivas | Aprobación humana |
| Rollback código | Independiente del esquema |
| SQLite | No |
| Kubernetes | No |
| Self-hosted runner | No |
| Imágenes | Python |
| Datos financieros en Git | Nunca |

---

## 41. Principio de cierre

La infraestructura debe ser suficientemente profesional para proteger un ledger financiero, pero suficientemente pequeña para que Erick pueda entenderla, operarla y reemplazar cualquier componente.

La arquitectura no debe depender de que n8n, GitHub Actions, Docker o un agente de IA sean permanentes.

El sistema debe poder seguir funcionando si cualquiera de esas piezas cambia.

**La automatización reduce trabajo; no sustituye la responsabilidad sobre los datos.**
