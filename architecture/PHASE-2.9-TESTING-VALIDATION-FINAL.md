# 2.8 — Testing & Validation Architecture

## 1. Objetivo

Definir cómo se verificará que el sistema funciona correctamente antes de considerarlo apto para uso real.

La estrategia de testing debe proteger especialmente:

- integridad del ledger financiero;
- precisión monetaria;
- idempotencia;
- correcciones append-only;
- autenticación entre n8n y Python;
- aislamiento de PostgreSQL;
- seguridad del contenedor;
- comportamiento conversacional de Telegram/n8n;
- compatibilidad entre código y esquema;
- generación de reportes/imágenes desde Python.

El principio rector es:

> **Los tests deben verificar las reglas ya decididas en la arquitectura; no deben introducir nuevas reglas de negocio por inferencia.**

---

## 2. Principios de testing

### 2.1 Python es la fuente de verdad del dominio

Los tests financieros deben ejecutarse directamente contra Python, sin depender de Telegram, n8n ni de un LLM.

Esto permite comprobar que:

- el dominio funciona de forma determinística;
- los cálculos monetarios son correctos;
- las correcciones preservan el historial;
- la idempotencia está garantizada;
- el sistema no depende de agentes de IA para mantener la integridad.

### 2.2 Las integraciones se prueban por separado

Telegram, n8n, FastAPI, PostgreSQL y servicios externos deben tener tests de integración específicos.

Un fallo de Telegram no debe confundirse con un fallo del dominio financiero.

### 2.3 Los LLM no son autoridad financiera

El LLM puede participar en parsing/fallback o generación narrativa, pero nunca decide:

- saldo;
- signo financiero;
- deuda;
- identidad financiera;
- correcciones;
- estado final del ledger.

Los tests deben verificar esta separación.

### 2.4 Los tests de producción deben ser mínimos y controlados

La validación en el VPS no debe insertar datos financieros reales innecesariamente.

Cuando sea posible, se utilizarán:

- datos sintéticos;
- usuarios de prueba;
- eventos identificados como pruebas;
- endpoints de health/check;
- consultas de solo lectura.

---

# 3. Capas de testing

La estrategia tendrá cinco capas:

```text
┌──────────────────────────────────────┐
│  E2E / Producción controlada         │
│  Telegram → n8n → FastAPI → DB       │
├──────────────────────────────────────┤
│  Integración                          │
│  API / PostgreSQL / Docker / n8n      │
├──────────────────────────────────────┤
│  Persistencia                         │
│  SQLAlchemy / PostgreSQL / Alembic   │
├──────────────────────────────────────┤
│  Dominio                              │
│  Decimal / ledger / corrections       │
├──────────────────────────────────────┤
│  Parsing / validación                 │
│  deterministic parser / LLM fallback  │
└──────────────────────────────────────┘
```

Cada capa debe poder ejecutarse independientemente cuando sea razonable.

---

# 4. Tests del dominio financiero

Estos son los tests de mayor prioridad.

## 4.1 Precisión monetaria

Verificar que todos los cálculos utilicen `Decimal` y que no exista pérdida de precisión por `float`.

Casos mínimos:

- `25.50 + 10.25 = 35.75`;
- `0.10 + 0.20 = 0.30`;
- múltiples transacciones con céntimos;
- división cuando corresponda;
- acumulación de muchas operaciones pequeñas;
- saldo exactamente igual a cero;
- saldo positivo;
- saldo negativo.

El resultado esperado debe compararse como valor monetario exacto, no mediante tolerancias propias de `float`.

## 4.2 Signo y dirección

Verificar explícitamente:

- `S > 0` → `erick_owes_mama`;
- `S < 0` → `mama_owes_erick`;
- `S = 0` → `direction = null`.

> **Errata (Fase 3, ciclo 2 — Claude ↔ Codex):** para `S = 0`, la referencia
> autoritativa es **PHASE-2.5 §13**, que define el valor de enum `no_debt`. La
> implementación y el contrato de API usan `no_debt`, no `null`. La línea
> anterior queda como histórica.

El consumidor de la API no debe tener que inferir el significado del signo.

## 4.3 Event types

El dominio debe aceptar únicamente los `event_type` definidos por el contrato.

Debe existir al menos:

- caso válido por cada tipo;
- tipo desconocido;
- tipo vacío;
- tipo malformado.

No debe existir un camino implícito que permita a un LLM inventar nuevos tipos.

---

# 5. Tests de ledger y correcciones

## 5.1 Append-only

Una corrección nunca debe sobrescribir silenciosamente el evento original.

Debe verificarse:

```text
Evento original
      │
      ├── permanece almacenado
      │
      └── queda SUPERSEDED
               │
               └── nuevo evento activo
```

## 5.2 Corrección de evento activo

Verificar que:

1. existe el evento original;
2. se crea el evento de corrección;
3. el original queda `SUPERSEDED`;
4. `superseded_by` apunta al nuevo evento;
5. el nuevo evento queda activo;
6. el saldo se recalcula correctamente.

Estas operaciones deben ocurrir dentro de una única transacción PostgreSQL.

## 5.3 Corrección de evento ya `SUPERSEDED`

Regla cerrada:

> **No se permite corregir directamente una transacción que ya está `SUPERSEDED`.**

La operación debe rechazarse.

Esto evita cadenas ambiguas de correcciones y obliga a que una nueva corrección apunte al evento activo correspondiente.

Debe existir un test que confirme el rechazo.

---

# 6. Idempotencia

La idempotencia es una propiedad de integridad crítica.

## 6.1 Restricción PostgreSQL

La `idempotency_key` debe tener una restricción `UNIQUE` a nivel de PostgreSQL.

No es suficiente implementar:

```text
SELECT → si no existe → INSERT
```

como mecanismo exclusivo.

La base de datos debe ser capaz de impedir atómicamente la duplicación.

## 6.2 Tests mínimos

### Mismo evento, una vez

Enviar dos veces la misma `idempotency_key`.

Resultado:

- una sola transacción efectiva;
- segundo procesamiento tratado como duplicado/idempotente;
- no se altera el saldo dos veces.

### Concurrencia

Simular dos solicitudes concurrentes con la misma clave.

Resultado:

- PostgreSQL permite una sola inserción;
- la segunda operación encuentra la violación de unicidad;
- Python transforma ese conflicto en una respuesta idempotente controlada;
- no existen dos eventos equivalentes.

## 6.3 Orden con parsing/LLM

La comprobación de idempotencia debe realizarse **antes de invocar el parser o el fallback LLM** cuando la solicitud ya contiene una `idempotency_key`.

Objetivos:

- evitar llamadas LLM innecesarias;
- evitar costos duplicados;
- evitar que el mismo evento sea parseado dos veces con resultados potencialmente distintos;
- preservar el significado de idempotencia.

---

# 7. Estado conversacional y confirmación

El flujo de Telegram es multi-turno y n8n mantiene el estado conversacional.

El flujo real debe incluir explícitamente:

```text
Usuario
   ↓
Selecciona tipo
   ↓
n8n guarda estado
   ↓
Usuario escribe monto / descripción
   ↓
n8n recupera estado
   ↓
Python parsea/valida
   ↓
n8n presenta resumen
   ↓
Usuario confirma
   ↓
n8n solicita registro definitivo
   ↓
FastAPI
   ↓
PostgreSQL
```

## 7.1 Regla de confirmación

La transacción **no se registra definitivamente antes de la confirmación explícita del usuario**.

El resumen mostrado debe representar los datos que serán registrados.

Debe probarse:

- cancelación antes de confirmar → no se registra;
- modificación antes de confirmar → solo se registra la versión finalmente confirmada;
- confirmación → se registra una sola vez;
- doble confirmación/reintento → idempotencia evita duplicado.

## 7.2 Momento de generación de `idempotency_key`

La `idempotency_key` se genera **cuando la operación está lista para ser confirmada**, no al iniciar la conversación.

Una vez generada:

1. se almacena en el estado conversacional de n8n;
2. permanece asociada al resumen presentado;
3. el botón/mensaje de confirmación reutiliza esa misma clave;
4. todos los reintentos de la misma confirmación utilizan la misma clave.

Por tanto:

```text
Recolección
    ↓
Resumen
    ↓
Generar idempotency_key
    ↓
Guardar estado en n8n
    ↓
Confirmar
    ↓
POST /transactions
    ↓
UNIQUE(idempotency_key)
```

Esto garantiza que un doble clic, retry de webhook o timeout no genere dos transacciones.

---

# 8. Parsing

## 8.1 Parser determinístico

Debe probarse primero el parser determinístico.

Casos mínimos:

- `S/ 35.50 taxi`;
- `35.50 taxi`;
- `35,50 taxi`;
- monto sin descripción;
- descripción sin monto;
- texto ambiguo;
- texto vacío;
- moneda no soportada;
- múltiples números.

## 8.2 Fallback LLM

El fallback LLM solo debe activarse cuando el parser determinístico no pueda producir una estructura válida según las reglas definidas.

Debe comprobarse que la salida del LLM pase por validación estructurada antes de llegar al dominio.

No se debe permitir que el LLM produzca directamente:

- `balance`;
- `signed_amount`;
- `signed_effect`;
- `event_type` arbitrario;
- `person_id` arbitrario.

## 8.3 Certeza del parsing

La arquitectura todavía no define un sistema formal de `confidence_score`.

Por tanto, no se debe convertir "nivel suficiente de certeza" en una regla numérica inventada durante testing.

Queda como pendiente explícito de diseño/implementación:

> Definir, si resulta necesario, cómo se determina que una extracción requiere confirmación adicional o rechazo.

Mientras tanto, la seguridad debe descansar en:

- parser determinístico;
- esquema de salida;
- validación Python;
- confirmación explícita del usuario;
- rechazo de estructuras inválidas.

---

# 9. Tests de API

## 9.1 `POST /transactions`

Debe probarse:

- request válido estructurado;
- request válido con `raw_text`;
- monto inválido;
- descripción ausente cuando sea obligatoria;
- `event_type` inválido;
- `telegram_user_id` desconocido;
- `idempotency_key` duplicada;
- campos prohibidos;
- JSON malformado.

### Campos nunca aceptados como autoridad desde n8n

No se deben aceptar como valores financieros autoritativos:

- `balance`;
- `signed_amount`;
- `signed_effect`.

Python debe calcularlos.

## 9.2 `GET /balance`

Probar:

```text
S > 0 → erick_owes_mama
S < 0 → mama_owes_erick
S = 0 → no_debt      (errata §4.2: PHASE-2.5 §13 es autoritativo, no `null`)
```

Además:

- respuesta consistente;
- precisión monetaria;
- usuario autorizado;
- usuario no autorizado.

## 9.3 Correcciones

`POST /transactions/{id}/corrections` debe probar:

- corrección válida;
- ID inexistente;
- ID ya `SUPERSEDED`;
- datos inválidos;
- conflicto de concurrencia;
- rollback transaccional ante error.

---

# 10. Resolución de identidad

Python es responsable de resolver:

```text
telegram_user_id
        ↓
person_id interno
```

n8n no debe enviar arbitrariamente un `person_id` financiero como autoridad.

Tests:

- usuario Telegram conocido;
- usuario desconocido;
- usuario deshabilitado, si esa capacidad existe;
- intento de enviar `person_id` inconsistente;
- resolución determinística.

---

# 11. Tests de autenticación API

La comunicación producción será:

```text
n8n
 ↓
HTTP interno
 ↓
FastAPI
```

FastAPI no estará expuesto directamente a Internet.

Debe existir autenticación entre n8n y FastAPI mediante un secreto/API key compartido almacenado como secreto de infraestructura.

Tests:

- credencial válida → `200/2xx`;
- credencial ausente → `401`;
- credencial incorrecta → `401`;
- credencial malformada → rechazo;
- endpoint inaccesible desde Internet;
- endpoint accesible desde la red interna autorizada.

El secreto nunca debe aparecer en:

- código fuente;
- Git;
- logs;
- respuestas API;
- screenshots;
- fixtures de testing.

---

# 12. Tests de PostgreSQL

## 12.1 Aislamiento

Verificar:

- base de datos dedicada del proyecto;
- esquema controlado;
- rol dedicado;
- n8n no utiliza las credenciales del proyecto;
- FastAPI utiliza únicamente el rol de aplicación correspondiente.

## 12.2 Privilegios mínimos

El rol dedicado del proyecto debe verificarse explícitamente.

Debe comprobarse mediante PostgreSQL que:

```text
rolsuper     = false
rolcreatedb  = false
rolcreaterole = false
```

También debe verificarse que no tenga privilegios administrativos equivalentes innecesarios.

Este test es obligatorio porque el VPS ya contiene un patrón administrativo existente (`gonex`) que **no debe copiarse** al nuevo rol.

## 12.3 Restricción de idempotencia

Debe existir un test de esquema que compruebe que `idempotency_key` tiene una restricción `UNIQUE`.

---

# 13. Tests de migraciones Alembic

Las migraciones se gestionan con Alembic.

## 13.1 Migraciones aditivas

Las migraciones normales/aditivas pueden ejecutarse automáticamente en CD cuando estén aprobadas y formen parte del release.

## 13.2 Migraciones potencialmente destructivas

Toda migración que pueda causar pérdida de datos requiere aprobación humana explícita antes de aplicarse en producción.

Ejemplos:

- `DROP TABLE`;
- `DROP COLUMN`;
- reducción destructiva de tipo;
- eliminación de información;
- transformaciones irreversibles.

No se debe permitir que un agente de IA decida automáticamente ejecutar una migración destructiva.

## 13.3 Rollback

Código y esquema son operaciones independientes.

Debe asumirse que:

```text
Rollback de código
≠
Rollback de esquema
```

Una imagen Docker anterior no garantiza compatibilidad con un esquema posterior.

Por ello, cada release debe considerar:

- versión del código;
- versión del esquema;
- compatibilidad entre ambas;
- posibilidad de rollback;
- necesidad de una migración de reversión.

No se debe asumir que `alembic downgrade` será siempre seguro en producción; su uso deberá evaluarse según la migración concreta.

---

# 14. Tests Docker

## 14.1 Imagen

Verificar:

- build reproducible;
- dependencias fijadas;
- imagen mínima razonable;
- ausencia de secretos embebidos.

## 14.2 Usuario no-root

El contenedor FastAPI debe ejecutarse como usuario no-root.

Debe existir un test/verificación explícita:

```bash
docker exec <container> id
```

y el resultado debe demostrar que el proceso no corre como `root`.

## 14.3 Healthcheck

Debe existir un mecanismo de healthcheck apropiado para determinar:

- aplicación levantada;
- API disponible;
- dependencia crítica de PostgreSQL disponible cuando corresponda.

No debe confundirse "contenedor running" con "servicio saludable".

---

# 15. Tests n8n

Se probará el workflow conversacional completo.

## Casos mínimos

1. `/start`;
2. selección de tipo;
3. almacenamiento del estado;
4. ingreso de monto/descripción;
5. recuperación del estado;
6. parsing;
7. resumen;
8. cancelación;
9. confirmación;
10. envío a FastAPI;
11. respuesta exitosa;
12. error de API;
13. retry;
14. doble confirmación;
15. usuario Telegram desconocido.

## Estado abandonado

El ciclo de vida exacto del estado conversacional queda como detalle de implementación pendiente.

Debe existir un mecanismo de expiración/limpieza para evitar sesiones huérfanas indefinidamente.

El timeout concreto no se fija en esta sección.

---

# 16. Tests de Telegram

La validación de Telegram se hará en producción controlada.

Debe comprobarse:

- webhook configurado correctamente;
- recepción de mensajes;
- recepción de botones/callbacks;
- respuesta del bot;
- comportamiento ante retry;
- funcionamiento de confirmación;
- funcionamiento de cancelación.

No se debe depender de Telegram para los tests unitarios del dominio.

---

# 17. Tests de reportes e imágenes

La generación de imágenes de reportes pertenece a Python.

Debe verificarse:

- generación correcta;
- datos representados corresponden al ledger;
- montos con precisión correcta;
- fechas correctas;
- ausencia de datos financieros de otro usuario;
- archivo generado correctamente;
- errores manejados sin corromper el ledger.

n8n solo orquesta la entrega.

---

# 18. Tests de privacidad

El sistema es un agente personal para dos usuarios.

Los datos financieros reales no deben aparecer en:

- GitHub;
- código;
- fixtures;
- logs;
- screenshots;
- documentación pública;
- mensajes de error;
- variables de entorno versionadas.

Las pruebas locales deben usar datos sintéticos siempre que sea posible.

## Backups

Los backups contienen datos financieros reales y forman parte del perímetro de privacidad.

El backup existente de PostgreSQL utiliza almacenamiento externo Backblaze B2. Antes de considerar el sistema plenamente operativo, debe verificarse:

- cifrado en tránsito;
- cifrado en reposo;
- control de acceso;
- retención;
- restauración;
- credenciales utilizadas.

Esto no implica eliminar el backup; implica reconocerlo formalmente como parte del perímetro de datos sensibles.

---

# 19. Seguridad de usuarios desconocidos

Dado que el alcance inicial es un agente personal para únicamente dos usuarios, no se introduce un sistema empresarial de rate limiting o anti-abuse.

La regla es:

```text
telegram_user_id desconocido
        ↓
rechazo
        ↓
no acceso al dominio financiero
```

La ausencia de rate limiting avanzado es una decisión consciente de alcance, no una omisión.

Si el sistema se amplía a público general, esta decisión deberá revisarse.

---

# 20. Tests de CI/CD

El pipeline deberá ejecutar al menos:

```text
Lint / validaciones básicas
        ↓
Tests unitarios
        ↓
Tests de integración
        ↓
Build Docker
        ↓
Verificaciones de seguridad
        ↓
Deploy
        ↓
Healthcheck
```

Los tests financieros no dependen de Telegram.

---

# 21. Tests post-deployment

Después del deployment en VPS:

1. comprobar contenedor;
2. comprobar healthcheck;
3. comprobar conectividad con PostgreSQL;
4. comprobar autenticación interna;
5. comprobar endpoint de salud;
6. verificar logs sin secretos;
7. ejecutar una prueba E2E controlada;
8. comprobar que no se creó un duplicado;
9. comprobar respuesta de Telegram;
10. registrar resultado del deployment.

La prueba E2E debe utilizar datos claramente identificables como prueba y minimizar cualquier impacto sobre el ledger real.

---

# 22. Criterios de aceptación

## Dominio

- [ ] Precisión monetaria con `Decimal`.
- [ ] Dirección del saldo inequívoca.
- [ ] Event types cerrados.
- [ ] Correcciones append-only.
- [ ] Evento `SUPERSEDED` no puede corregirse directamente.
- [ ] Idempotencia garantizada.

## PostgreSQL

- [ ] Base dedicada.
- [ ] Rol dedicado.
- [ ] `SUPERUSER = false`.
- [ ] `CREATEDB = false`.
- [ ] `CREATEROLE = false`.
- [ ] `UNIQUE(idempotency_key)`.
- [ ] Migraciones mediante Alembic.

## API

- [ ] FastAPI responde correctamente.
- [ ] Autenticación interna.
- [ ] No exposición pública.
- [ ] Errores estructurados.
- [ ] `raw_text` soportado por `POST /transactions`.
- [ ] Python calcula valores financieros.

## Telegram/n8n

- [ ] Estado multi-turno.
- [ ] Confirmación explícita.
- [ ] `idempotency_key` generada al preparar confirmación.
- [ ] Misma clave en retries.
- [ ] Cancelación sin registro.
- [ ] Usuario desconocido rechazado.

## Docker

- [ ] Backend en contenedor dedicado.
- [ ] Proceso no-root.
- [ ] Healthcheck.
- [ ] Sin secretos en imagen.

## CI/CD

- [ ] Tests ejecutados antes de deployment.
- [ ] Build reproducible.
- [ ] Migraciones gobernadas.
- [ ] Migraciones destructivas requieren aprobación humana.
- [ ] Rollback de código y esquema tratados separadamente.

## Privacidad

- [ ] No secretos en Git.
- [ ] No datos financieros reales en fixtures.
- [ ] No datos sensibles en logs.
- [ ] Backups tratados como datos sensibles.
- [ ] E2E controlado.

---

# 23. Observaciones operativas heredadas

La infraestructura actual presenta dos hallazgos que deben quedar registrados, aunque no formen parte del alcance inmediato del proyecto:

1. El backup existente presentó un fallo operativo documentado previamente (`b2: command not found`), por lo que su ejecución efectiva debe verificarse antes de confiar en él.
2. La base `thingsboard` aparece activa en PostgreSQL pero no estaba incluida en el array `BASES` del script de backup revisado.

Estos puntos pertenecen a la infraestructura general de GONEX y no deben mezclarse con la implementación del ledger, pero deben permanecer visibles hasta su resolución.

---

# 24. Pendientes explícitos

Los siguientes puntos quedan abiertos sin inventar decisiones adicionales:

1. Definir el mecanismo exacto de expiración del estado conversacional en n8n.
2. Definir si se requiere un `confidence_score` formal para parsing/LLM y, si es así, su semántica.
3. Verificar configuración de cifrado y acceso del backup en B2.
4. Verificar restauración real de backups.
5. Definir estrategia concreta de compatibilidad entre releases y migraciones.
6. Definir pruebas E2E sintéticas que no contaminen el ledger real.
7. Revisar rate limiting si el proyecto deja de ser un agente personal de dos usuarios.
8. Revisar `Person.role` y la evolución futura del modelo de personas en la sección de modelo de datos definitivo.
9. Resolver el significado de `S` si el sistema evoluciona a más de dos personas.
10. Mantener sincronizadas las referencias entre 2.4, 2.7 y 2.8 respecto al flujo conversacional y confirmación.

---

# 25. Regla de cierre

La sección 2.8 se considera cerrada cuando un implementador puede responder, sin inventar reglas:

- qué se prueba;
- en qué capa se prueba;
- qué resultado se espera;
- qué reglas financieras son inmutables;
- cómo se verifica la idempotencia;
- cómo se verifica la seguridad;
- cómo se verifica el aislamiento de PostgreSQL;
- cómo se verifica el flujo conversacional;
- cómo se gobiernan las migraciones;
- qué se prueba localmente;
- qué se prueba en producción;
- y qué decisiones permanecen explícitamente pendientes.

La arquitectura debe poder seguir funcionando aunque posteriormente se cambien:

- n8n;
- Telegram;
- FastAPI;
- el proveedor LLM;
- agentes de IA;
- el mecanismo de CI/CD.

La integridad financiera no debe depender de ninguna de esas herramientas.
