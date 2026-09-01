# PHASE 2.11 — SECURITY & SECRETS

**Proyecto:** Personal Expense Ledger — Telegram + n8n + Python + PostgreSQL
**Fase:** 2 — Technical Design
**Sección:** 2.11 — Security + Secrets (consolidación)
**Estado:** CERRADO — validado con evidencia real del VPS y GitHub
**Fecha:** 2026-08-31

---

## 1. Propósito

Consolidar en un único documento las decisiones de seguridad y manejo de secretos ya establecidas a lo largo de 2.1–2.10, sin reabrir ninguna. Esta sección no introduce nuevas reglas financieras, de dominio o de arquitectura — es un documento de referencia.

---

# 2. Hallazgos de verificación de esta sección

## 2.1 Clave SSH de deployment — NO existe todavía

Se verificó en el VPS:

```text
~/.ssh/authorized_keys contiene únicamente:
  - gonex-pc-ubuntu     (clave personal de Erick, PC Ubuntu)
  - gonex-laptop-win11  (clave personal de Erick, laptop Windows)
```

No existe ningún usuario adicional del sistema dedicado a deployment (solo `erick` entre los usuarios no estándar), y el log de autenticación (`/var/log/auth.log`) confirma que todos los accesos SSH recientes provienen de la clave personal de Erick, desde su IP habitual.

Se verificó también el repositorio `gonex-WebSite`:

* No existen workflows de GitHub Actions propios (el único archivo `.github/workflows/*.yml` encontrado pertenece a una dependencia de `node_modules`, no al proyecto).
* El repositorio `gonex-web` en GitHub confirma **cero secrets configurados** (ni de repositorio ni de entorno).

**Conclusión:** el despliegue automático que Erick recordaba para `gonex.pe` no ocurre vía GitHub Actions + SSH al VPS — el propio `README.md` de `gonex-infra` confirma que `gonex.pe` se sirve mediante **Netlify**, no desde el VPS. No existe hoy ninguna clave SSH de CI/CD hacia el VPS, para ningún proyecto.

**Decisión (ya tomada por Erick):** este proyecto usará una clave SSH de deployment separada de las claves personales, dedicada exclusivamente al pipeline de CI/CD. Como no existe ninguna clave de este tipo hoy, se crea desde cero — no hay nada que migrar ni reemplazar.

## 2.2 Causa raíz del backup roto — identificada

Se verificó en el VPS:

```text
which b2                     → /home/erick/.local/bin/b2
b2 version                   → 4.6.0 (funciona correctamente en sesión interactiva)
pip3 show b2                 → instalado en /home/erick/.local/lib/python3.12/site-packages
```

El binario **sí está instalado** y funciona cuando Erick lo ejecuta manualmente desde su sesión SSH interactiva. El error `b2: command not found` que aparece en el cron (`backup.log`) es una causa clásica y distinta de lo que Erick sospechaba: **cron no carga el mismo `PATH` que una sesión interactiva**, y `~/.local/bin` (donde vive `b2`) típicamente no está en el `PATH` mínimo que usa cron. No tiene relación con la suspensión de pago de ThingsBoard.

**Conclusión:** el backup lleva roto por un problema de `PATH` en el entorno de cron, no por falta de instalación ni por la baja de ThingsBoard. Es una corrección simple (usar la ruta completa `/home/erick/.local/bin/b2` en el script, o exportar `PATH` explícitamente al inicio del cron job) — pertenece a la infraestructura GONEX existente, no a este proyecto, y se documenta aquí como hallazgo heredado, igual que en 2.6/2.7.

## 2.3 Cifrado del backup en Backblaze B2 — pendiente de verificar

No se contó con la información necesaria para confirmar cifrado en tránsito/reposo del bucket `gonex-backups`. Queda como pendiente explícito (§8) antes de que la base de datos de este proyecto se incorpore al mecanismo de backup.

---

# 3. Secrets Management (heredado de 2.6/2.7 — sin cambios)

Nunca entran a Git, bajo ninguna circunstancia:

```text
API keys (Anthropic, otros proveedores)
Telegram bot token
Credenciales de PostgreSQL
Internal API token (n8n → FastAPI)
SSH private keys (personales y de deployment)
n8n encryption key
Cualquier .env real
```

El repositorio contiene únicamente `.env.example` con nombres de variable y valores ficticios:

```env
DATABASE_URL=postgresql+psycopg://<DEDICATED_USER>:<PASSWORD>@<HOST>:5432/<DEDICATED_DB>
TELEGRAM_BOT_TOKEN=<SET_IN_RUNTIME>
API_INTERNAL_TOKEN=<SET_IN_RUNTIME>
LLM_API_KEY=<SET_IN_RUNTIME>
ENVIRONMENT=<local|production>
```

Los valores reales existen únicamente en los entornos correspondientes (local: `.env` no versionado; producción: variables de entorno del contenedor / GitHub Secrets para el pipeline).

---

# 4. Accesos (heredado + hallazgo de esta sección)

## 4.1 Telegram

Solo dos `telegram_user_id` autorizados (Erick, mamá), configurados como configuración controlada del sistema, no hardcodeados en código de dominio. Un `telegram_user_id` desconocido es rechazado por Python — no crea `Person` ni `Transaction` (2.6 §12).

## 4.2 Autenticación n8n → Python

API key de servicio estática, almacenada como secreto:

```http
Authorization: Bearer <INTERNAL_SERVICE_TOKEN>
```

No se usa autenticación basada únicamente en "misma red Docker" (2.6 §11, 2.7 §11).

## 4.3 SSH de deployment (nuevo, definido en esta sección)

Dado el hallazgo de §2.1, se establece:

* Se crea una clave SSH nueva, dedicada exclusivamente al pipeline de CI/CD de este proyecto — nunca la clave personal de Erick (`gonex-pc-ubuntu` / `gonex-laptop-win11`).
* La clave privada se almacena como GitHub Secret (`DEPLOY_SSH_KEY` o nombre equivalente), nunca en el repositorio.
* La clave pública se añade a `~/.ssh/authorized_keys` del VPS, idealmente restringida mediante `command=` o un usuario del sistema dedicado sin `sudo`, limitado a las operaciones necesarias para el deployment de este proyecto (reiniciar/actualizar sus propios contenedores Docker).
* El alcance exacto de esa restricción (usuario dedicado vs. `authorized_keys` con `command=` forzado) queda como detalle de implementación — el requisito no negociable es que **no sea la misma clave con la que Erick administra el VPS completo**.

## 4.4 PostgreSQL

Rol dedicado del proyecto, sin `SUPERUSER`, `CREATEDB` ni `CREATEROLE` (regla dura ya establecida en 2.6 §3 y 2.7 §6, verificada como corrección necesaria en revisión cruzada). Nunca se usan las credenciales del rol administrativo `gonex` existente.

---

# 5. Docker (heredado de 2.7 — sin cambios)

* Contenedor del backend corre como usuario no-root cuando sea viable (2.7 §21).
* No se asume pertenencia automática a `docker_gonex-network`; el alcance de red se limita a lo estrictamente necesario (2.7 §8, 2.6 §15).
* El backend no publica su puerto al host salvo necesidad operativa explícita — preferencia por comunicación interna de contenedores (2.7 §10).
* PostgreSQL no se expone públicamente; el puerto `5432` nunca se abre a Internet (2.6 §14, 2.7 §6).

---

# 6. GitHub (heredado + precisión de esta sección)

* El repositorio es público (decisión de Fase 1).
* GitHub Actions usa **GitHub-hosted runners**, no self-hosted (2.7 §25 — menor superficie de ataque, sin infraestructura adicional en el VPS).
* Los secretos del pipeline (API key interna para tests si aplica, clave SSH de deployment) se almacenan como **GitHub Secrets**, nunca como archivos versionados (2.7 §19).
* Verificado en esta sección: el repositorio `gonex-web` (referencia de otro proyecto de Erick) no tiene secrets configurados y no tiene workflows propios — confirma que no existe ningún patrón previo de GitHub Actions + VPS que este proyecto deba replicar o del que deba heredar configuración. Se parte de cero, sin arrastrar configuración de otro repo.
* Permisos del workflow (`permissions:` en el YAML) deben limitarse a lo mínimo necesario (lectura de contenido, sin permisos de escritura innecesarios) — detalle de implementación a definir en 2.7/CI concreto, mencionado aquí como principio.

---

# 7. Scanning y verificación pre-publicación

Antes de cualquier push que exponga el repositorio (o cambios sensibles), debe verificarse manualmente o mediante herramienta ligera (ej. `git-secrets`, `gitleaks`, o revisión manual de diff) que no se haya colado:

```text
Tokens
API keys
Credenciales de base de datos
Capturas reales de Yape/Plin
Descripciones o montos financieros reales
Telegram user_id reales (si se considera sensible)
```

No se introduce una plataforma de scanning compleja (no es necesaria para un bot personal de dos usuarios) — un chequeo ligero pre-commit/pre-push es suficiente para v1, coherente con el principio de proporcionalidad ya aplicado en 2.8 §38.

---

# 8. Pendientes explícitos de esta sección

1. **Cifrado de Backblaze B2** (tránsito y reposo) — no verificado, pendiente antes de incorporar la DB de este proyecto al backup general.
2. **Corrección del `PATH` en el cron de backup** (`b2: command not found`) — pertenece a la infraestructura GONEX existente, no bloquea este proyecto, pero debe resolverse antes de que el backup de este proyecto dependa de ese mecanismo.
3. **Alcance exacto de restricción de la clave SSH de deployment** (usuario dedicado sin sudo vs. `command=` forzado en `authorized_keys`) — a definir en implementación, con el único requisito duro de que no sea la clave personal de Erick.
4. **Herramienta concreta de scanning pre-publicación** (si alguna, más allá de revisión manual) — a decidir en implementación, sin bloquear el cierre de esta sección.

Ninguno de estos pendientes es una laguna de diseño — son detalles de implementación ya acotados por reglas duras ya cerradas (ej. "nunca la clave personal", "nunca sin cifrado verificado antes de subir datos reales").

---

# 9. Principios de seguridad — lista consolidada final

1. PostgreSQL no público.
2. Python API no pública.
3. n8n es el único consumidor previsto de la API en producción.
4. n8n → Python requiere autenticación (API key de servicio).
5. Python valida nuevamente todo dato recibido, sin confiar en n8n.
6. Identidad de Telegram resuelta únicamente por Python.
7. Usuarios desconocidos son rechazados sin crear registros.
8. Secretos nunca entran a Git (código, `.env`, ni historial).
9. El backend nunca confía en `balance`, `signed_amount` o `signed_effect` enviados por n8n.
10. Datos financieros reales nunca se versionan (código, tests, logs, imágenes de reportes).
11. Rol de base de datos con privilegios mínimos: sin `SUPERUSER`, `CREATEDB`, `CREATEROLE`.
12. Migraciones reproducibles vía Alembic; las destructivas requieren aprobación humana (2.8 §26).
13. Rollback de código y de esquema son operaciones independientes, ninguna se asume automática (2.8 §27).
14. Clave SSH de deployment separada de las claves personales de Erick, con alcance restringido al proyecto.
15. GitHub Actions usa runners hospedados por GitHub, no self-hosted.
16. Backups se tratan como datos sensibles — mismo estándar de privacidad que el ledger en producción.

---

## Estado

**2.11 — CERRADO.**

Siguiente y último documento de Fase 2: **2.12 — Plan de trabajo Codex ↔ Claude Code**, tras el cual la Fase 2 completa queda cerrada y comienza la implementación.
