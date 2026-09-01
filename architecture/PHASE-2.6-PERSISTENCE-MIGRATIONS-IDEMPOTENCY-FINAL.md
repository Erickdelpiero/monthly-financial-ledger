# 2.6 — Persistence, Migrations, Idempotency & Operational Safety

**Proyecto:** Personal Financial Ledger / Telegram Expense Assistant  
**Fase:** 2 — Technical Design  
**Sección:** 2.6  
**Estado:** FINAL — validado tras revisión cruzada GPT ↔ Claude  
**Objetivo:** definir cómo se persisten los datos, cómo se gestionan cambios de esquema, cómo se garantiza la idempotencia y qué controles operativos protegen la integridad del ledger.

---

## 1. Propósito

Esta sección define las decisiones técnicas de persistencia y seguridad operacional que implementarán Codex/Claude Code.

El objetivo principal es preservar la integridad del ledger financiero sin depender de inferencias de agentes, LLMs o workflows de n8n.

Principios:

- PostgreSQL es la base de datos oficial de v1.
- La base de datos del proyecto será dedicada dentro de la instancia PostgreSQL existente de GONEX.
- El proyecto tendrá un rol PostgreSQL dedicado y de privilegio mínimo.
- La idempotencia será garantizada también a nivel de PostgreSQL mediante una restricción `UNIQUE`.
- Las operaciones financieras compuestas deben ser atómicas.
- Las migraciones de esquema serán explícitas y versionadas.
- Los datos financieros reales nunca deben entrar al repositorio público.
- Los backups forman parte de la superficie de privacidad y deben tratarse como datos financieros reales.

---

# 2. Decisión de base de datos

## 2.1 PostgreSQL

Se utilizará **PostgreSQL** en desarrollo y producción.

La decisión se mantiene respecto de las fases anteriores y no se reabre la alternativa SQLite.

### Motivos

- Ya existe PostgreSQL 16 operativo en el VPS.
- El proyecto necesita integridad transaccional.
- Se requiere una garantía fuerte de idempotencia mediante constraints.
- El modelo de correcciones requiere operaciones atómicas.
- PostgreSQL permite separar base de datos, esquema y rol con privilegios mínimos.
- Mantener el mismo motor entre desarrollo y producción reduce diferencias de comportamiento.

---

# 3. Aislamiento de la base de datos

El proyecto utilizará una **base de datos propia** dentro del contenedor `gonex-postgres`.

No utilizará la base `n8n`.

Conceptualmente:

```text
gonex-postgres
│
├── n8n
│   └── datos internos de n8n
│
├── [otras bases existentes de GONEX]
│
└── financial_ledger
    └── datos del proyecto
```

El nombre definitivo de la base puede establecerse durante la implementación, pero deberá ser inequívoco y específico del proyecto.

---

# 4. Rol PostgreSQL dedicado

El proyecto utilizará un rol propio.

Ejemplo conceptual:

```text
financial_ledger_app
```

Este rol:

- puede conectarse a la base dedicada;
- puede operar sobre el esquema propio del proyecto según los permisos definidos;
- no necesita acceso a la base `n8n`;
- no utilizará las credenciales administrativas existentes de GONEX.

## 4.1 Prohibiciones obligatorias

El rol de aplicación **NUNCA** deberá tener:

```text
SUPERUSER
CREATEDB
CREATEROLE
```

Tampoco deberá recibir privilegios administrativos equivalentes por comodidad.

La configuración debe poder verificarse mediante PostgreSQL.

El objetivo es que una eventual exposición de las credenciales de aplicación no permita administrar la instancia PostgreSQL completa ni afectar otras bases de GONEX.

---

# 5. Acceso de la aplicación

La aplicación Python utilizará exclusivamente las credenciales del rol dedicado.

Conceptualmente:

```text
FastAPI
   │
   │ PostgreSQL connection
   ▼
financial_ledger
```

No se permitirá que la aplicación:

- utilice el rol administrativo `gonex`;
- utilice credenciales de `n8n`;
- consulte o modifique tablas internas de n8n;
- dependa de credenciales administrativas de la infraestructura.

---

# 6. ORM y acceso a datos

Se utilizarán:

- **SQLAlchemy** como ORM / capa de acceso a datos.
- **Alembic** para migraciones de esquema.

La razón es mantener:

- modelos explícitos;
- transacciones controladas;
- migraciones versionadas;
- trazabilidad de cambios de esquema;
- compatibilidad con el flujo de desarrollo local → GitHub → VPS.

No se utilizará un sistema de migraciones manuales basado únicamente en scripts SQL ad-hoc.

---

# 7. Idempotencia

La idempotencia es un requisito funcional y de integridad del sistema.

El mismo evento lógico recibido más de una vez no debe crear múltiples transacciones financieras.

Esto es especialmente importante porque Telegram utiliza webhooks y un evento puede ser entregado nuevamente.

## 7.1 Regla obligatoria

La idempotencia deberá estar respaldada por una **restricción `UNIQUE` a nivel de PostgreSQL**.

No será suficiente implementar:

```text
SELECT → comprobar existencia → INSERT
```

como mecanismo único, porque dos solicitudes concurrentes podrían superar simultáneamente la comprobación.

La garantía deberá recaer en PostgreSQL:

```text
idempotency_key
       │
       ▼
UNIQUE constraint
       │
       ├── primer evento → INSERT exitoso
       │
       └── duplicado → conflicto de unicidad
```

Python deberá capturar el conflicto y responder de forma determinista según el contrato definido en 2.5.

---

# 8. Clave de idempotencia

La forma exacta de construir la clave se definirá durante la implementación de persistencia, pero deberá cumplir:

- ser determinística;
- representar el evento lógico de origen;
- ser estable ante reintentos;
- estar almacenada en PostgreSQL;
- tener una restricción `UNIQUE`.

La clave no debe depender de información financiera recalculada de forma no determinística por un LLM.

El diseño definitivo deberá considerar el identificador del evento de Telegram/origen cuando corresponda.

---

# 9. Transacciones y atomicidad

Las operaciones que modifican más de una entidad o registro deberán ejecutarse dentro de una transacción PostgreSQL.

Especialmente:

### Corrección

```text
BEGIN
  crear nueva transacción
  marcar transacción anterior como SUPERSEDED
COMMIT
```

Si cualquier parte falla:

```text
ROLLBACK
```

No debe existir un estado en el que:

- la nueva corrección exista pero la anterior continúe `ACTIVE`;
- la anterior quede `SUPERSEDED` pero la nueva transacción no exista.

---

# 10. Correcciones del ledger

Las correcciones mantienen el modelo definido en 2.3.

Una corrección:

- no elimina físicamente el evento original;
- crea una nueva transacción;
- marca la anterior como `SUPERSEDED`;
- conserva la trazabilidad mediante `superseded_by`;
- puede modificar el evento completo, incluyendo `event_type`, monto, descripción y fecha cuando corresponda.

No existe en v1 una ventana temporal técnica que bloquee correcciones de eventos antiguos.

El principio de uso es corregir preferentemente dentro del período mensual actualmente abierto, pero esto es una regla operativa, no un bloqueo técnico.

---

# 11. Cadenas de corrección

Las correcciones pueden encadenarse:

```text
A → B → C
```

donde:

```text
A = SUPERSEDED
B = SUPERSEDED
C = ACTIVE
```

Para calcular el ledger:

```text
WHERE status = ACTIVE
```

es suficiente.

No es necesario recorrer la cadena para calcular el saldo.

La cadena se conserva para auditoría y trazabilidad.

---

# 12. Rechazo de correcciones inválidas

Si una solicitud intenta corregir una transacción que ya está `SUPERSEDED`, la operación será **rechazada**.

No se resolverá automáticamente hacia la transacción más reciente.

El consumidor deberá utilizar el último evento activo de la cadena.

Esto evita ambigüedad y mantiene el contrato explícito.

---

# 13. Integridad del dominio

PostgreSQL deberá reforzar, cuando corresponda, las invariantes críticas mediante:

- `NOT NULL`;
- `CHECK`;
- `UNIQUE`;
- claves foráneas;
- tipos numéricos adecuados;
- constraints de integridad.

La base de datos no será la única capa de validación: Python seguirá siendo responsable de las reglas de dominio.

Principio:

```text
Python = reglas de negocio
PostgreSQL = persistencia + integridad estructural
```

---

# 14. Montos financieros

Los montos se persistirán utilizando un tipo decimal exacto compatible con PostgreSQL.

No se utilizará `float`.

El backend Python utilizará `Decimal`.

Esto garantiza que los céntimos sean tratados correctamente.

Ejemplo conceptual:

```text
25.50
100.00
0.75
```

---

# 15. Migraciones

Alembic será el mecanismo oficial para evolucionar el esquema.

Flujo conceptual:

```text
Modelo SQLAlchemy
      │
      ▼
Alembic migration
      │
      ▼
PostgreSQL development
      │
      ▼
Tests
      │
      ▼
Deployment
      │
      ▼
PostgreSQL production
```

Las migraciones deberán:

- estar versionadas en Git;
- ser revisables;
- ejecutarse de forma explícita;
- ser probadas antes de producción;
- permitir reconstruir el esquema desde cero.

No se modificará directamente el esquema productivo como método habitual.

---

# 16. Desarrollo local

El desarrollo de Python y PostgreSQL se validará localmente antes del deployment.

El entorno local deberá reproducir:

- PostgreSQL;
- esquema;
- migraciones;
- reglas de integridad;
- tests del dominio;
- tests de persistencia.

No se utilizará la base de datos productiva como base de pruebas.

---

# 17. Separación entre desarrollo y producción

Conceptualmente:

```text
LOCAL
Python + FastAPI + PostgreSQL
        │
        ▼
Tests
        │
        ▼
GitHub
        │
        ▼
Deployment
        │
        ▼
VPS
Python + FastAPI + PostgreSQL dedicado
```

Telegram/n8n se probarán como integración de producción una vez desplegado el backend.

---

# 18. Backend no expuesto a Internet

FastAPI no deberá exponerse directamente a Internet.

En producción:

```text
Telegram
   │
   ▼
Nginx / n8n
   │
   ▼
red interna
   │
   ▼
FastAPI
   │
   ▼
PostgreSQL
```

El backend deberá aceptar únicamente tráfico interno/autorizado según el diseño de despliegue definido posteriormente.

---

# 19. Seguridad de credenciales

Las credenciales reales:

- no se almacenan en Git;
- no se almacenan en el código;
- no se almacenan en documentación pública;
- no se incluyen en ejemplos reales;
- no se incluyen en tests versionados.

Se utilizarán variables de entorno y mecanismos seguros de configuración.

El `.env.example` solo contendrá nombres de variables y valores ficticios.

---

# 20. Logging

Los logs deben ser útiles para diagnóstico sin convertirse en una copia de los datos financieros.

Se podrá registrar:

- timestamp;
- nivel;
- endpoint;
- request/correlation ID;
- resultado de la operación;
- códigos de error;
- identificadores técnicos no sensibles.

No se registrará innecesariamente:

- montos reales;
- descripciones de gastos;
- contenido completo de mensajes de Telegram;
- credenciales;
- tokens;
- secretos;
- payloads financieros completos.

---

# 21. Backups

Durante la revisión de la infraestructura existente se detectó que el mecanismo actual de backup presenta un problema operativo:

```text
b2: command not found
```

El script existente no está funcionando correctamente en el estado observado.

Este hallazgo queda documentado deliberadamente y no se debe ocultar.

Antes de considerar la infraestructura de backup como confiable, deberá:

1. corregirse el problema del comando/dependencia;
2. probarse un backup real;
3. verificar que el archivo llegue correctamente al almacenamiento;
4. probarse un restore;
5. comprobarse periódicamente el resultado.

---

# 22. Inclusión de la nueva base en backups

La base dedicada del proyecto deberá incorporarse al mecanismo de backup existente una vez que el sistema esté implementado.

No se creará necesariamente un sistema paralelo si el backup de infraestructura puede extenderse de forma segura.

La inclusión deberá verificarse mediante una restauración real.

---

# 23. Privacidad de los backups

Los backups de este proyecto contienen **datos financieros reales**.

Por tanto, aunque se almacenen fuera del VPS, deben considerarse información privada.

La integración con Backblaze B2 u otro almacenamiento externo deberá evaluarse bajo este criterio:

```text
DB privada
   │
   ▼
backup
   │
   ▼
almacenamiento externo
```

Antes de dar por cerrado el proceso de backup deberá verificarse:

- cifrado en tránsito;
- protección/cifrado en reposo según la configuración utilizada;
- control de acceso;
- credenciales separadas;
- posibilidad real de restore.

La ubicación externa del backup no convierte los datos en públicos.

---

# 24. Gap preexistente de infraestructura

Durante la revisión del backup existente también se observó que `thingsboard` aparece como base activa de PostgreSQL pero no figura en el array `BASES` del script de backup.

Esto es un **gap preexistente de la infraestructura GONEX**, no una responsabilidad funcional de este proyecto.

Debe quedar documentado para evitar confundir:

```text
problema existente de GONEX
        ≠
problema introducido por este proyecto
```

Su corrección queda fuera del alcance de este piloto, salvo que posteriormente se decida como trabajo independiente de infraestructura.

---

# 25. Datos financieros reales y Git

Este proyecto tiene una excepción explícita respecto al patrón observado en `monthly-sop-automation`.

En `monthly-sop-automation`, `output/` se conserva en Git como evidencia.

**Ese patrón NO aplica aquí.**

Para este proyecto:

> Ningún dato financiero real, generado o de ejecución debe ser commiteado al repositorio público.

Esto incluye:

- transacciones;
- saldos;
- reportes;
- imágenes de reportes;
- exportaciones;
- dumps;
- logs con datos financieros;
- payloads reales;
- datos de Telegram;
- archivos temporales de ejecución.

Los tests utilizarán datos sintéticos.

---

# 26. Restauración y disaster recovery

El sistema no se considerará operacionalmente confiable solo porque exista un archivo de backup.

Debe demostrarse:

```text
backup
  ↓
restore
  ↓
PostgreSQL funcional
  ↓
ledger íntegro
```

La prueba de restore deberá verificarse antes de considerar cerrado el mecanismo de recuperación.

La frecuencia exacta de pruebas periódicas se definirá en la documentación operativa.

---

# 27. Estrategia de pruebas de persistencia

Se deberán cubrir como mínimo:

### Integridad

- montos decimales;
- campos obligatorios;
- valores inválidos;
- claves foráneas;
- estados válidos.

### Idempotencia

- primera inserción;
- mismo evento repetido;
- dos solicitudes concurrentes;
- conflicto de `UNIQUE`;
- respuesta determinista.

### Correcciones

- corrección normal;
- modificación de `event_type`;
- corrección encadenada;
- intento de corregir un `SUPERSEDED`;
- rollback ante fallo parcial.

### Migraciones

- migración desde cero;
- migración incremental;
- aplicación en entorno limpio;
- verificación posterior.

---

# 28. Contrato con la API

La persistencia debe respetar el contrato establecido en 2.5.

En particular:

- Python resuelve `telegram_user_id → person_id`;
- Python decide el parsing cuando recibe `raw_text`;
- Python calcula la lógica financiera;
- n8n no envía ni define `balance`, `signed_amount` o `signed_effect`;
- montos JSON se representan como strings;
- errores deben utilizar códigos estables.

La capa de persistencia no debe redefinir reglas del contrato API.

---

# 29. Decisiones diferidas

Quedan deliberadamente para implementación detallada:

- nombre final de la base;
- nombre final del rol;
- nombre exacto de la clave de idempotencia;
- estrategia exacta de generación de dicha clave;
- configuración concreta de SQLAlchemy;
- configuración concreta de Alembic;
- pooling;
- límites de conexiones;
- estrategia exacta de deployment;
- mecanismo concreto para proteger el HTTP interno;
- configuración definitiva del backup;
- periodicidad de pruebas de restore.

Estas decisiones no podrán contradecir las restricciones ya fijadas en esta sección.

---

# 30. Reglas no negociables para los agentes

Codex y Claude Code deberán respetar:

1. PostgreSQL, no SQLite.
2. Base de datos dedicada.
3. Rol de aplicación dedicado.
4. El rol de aplicación nunca tendrá `SUPERUSER`.
5. El rol de aplicación nunca tendrá `CREATEDB`.
6. El rol de aplicación nunca tendrá `CREATEROLE`.
7. Idempotencia respaldada por `UNIQUE` en PostgreSQL.
8. Correcciones atómicas.
9. No usar `float` para dinero.
10. No almacenar datos financieros reales en Git.
11. No usar la base productiva para pruebas.
12. No exponer FastAPI directamente a Internet.
13. No duplicar lógica financiera en n8n.
14. No utilizar credenciales administrativas existentes por comodidad.
15. Toda migración debe ser versionada.
16. Todo cambio de esquema debe poder reproducirse.
17. Los backups deben probarse mediante restore.
18. Los agentes no pueden inventar reglas financieras no definidas.

---

# 31. Estado de la sección

**2.6 — FINAL**

La arquitectura de persistencia queda suficientemente definida para continuar con el siguiente punto de Technical Design.

Las decisiones restantes son de implementación y no deben reabrir las decisiones de arquitectura ya cerradas.

**Siguiente sección: 2.7**
