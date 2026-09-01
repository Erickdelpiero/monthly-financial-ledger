# 2.5 — API & Service Contract

**Proyecto:** Personal Expense Ledger — Telegram + n8n + Python + PostgreSQL  
**Fase:** 2 — Technical Design  
**Sección:** 2.5 — API & Service Contract  
**Estado:** FINAL — listo para implementación  
**Última revisión:** 2026-08-30

---

## 1. Propósito

Definir el contrato explícito entre **n8n** y el backend **Python**, evitando que Codex o Claude Code tengan que inferir decisiones de dominio.

La arquitectura mantiene una separación estricta:

- **Telegram:** interfaz de usuario.
- **n8n:** orquestación del flujo conversacional.
- **Python/FastAPI:** lógica de dominio, validación definitiva, parsing, identidad, ledger y reportes.
- **PostgreSQL:** persistencia.
- **LLM:** fallback controlado del parser, nunca autoridad financiera.

---

## 2. Decisiones heredadas

Esta sección respeta las decisiones cerradas en 2.1–2.4:

1. PostgreSQL es la base de datos elegida.
2. El proyecto tendrá una base de datos y rol propios dentro de la instancia compartida de PostgreSQL.
3. Postgres no se expone públicamente.
4. El backend Python será un servicio independiente.
5. Se utilizará **FastAPI**.
6. n8n y Python se comunicarán mediante HTTP interno en producción.
7. Telegram utilizará **webhook HTTPS** hacia n8n.
8. n8n es dueño del estado conversacional multi-turno.
9. Python es la fuente única de verdad para las reglas del dominio.
10. n8n no implementará lógica financiera mediante Code Nodes.
11. `event_type`, identidad, saldo y efecto firmado no son decididos por el LLM.
12. El parser será determinístico primero y LLM como fallback.
13. Los montos viajarán como strings decimales en JSON.
14. Los reportes e imágenes serán generados por Python.
15. El sistema v1 es bilateral entre dos personas, aunque `Person` exista como entidad propia.
16. No se rastrea físicamente el dinero: se registra la obligación económica entre las personas.
17. Las correcciones reemplazan el evento completo y pueden encadenarse.
18. No existe una ventana temporal técnica que impida corregir eventos históricos.
19. La idempotencia es un requisito técnico.
20. Ningún dato financiero real debe entrar al repositorio público.

---

## 3. Responsabilidad del backend

Python debe ser responsable de:

- Resolver `telegram_user_id → person_id`.
- Validar la identidad.
- Parsear texto libre.
- Ejecutar parser determinístico.
- Invocar LLM únicamente como fallback.
- Validar el resultado del parser.
- Validar montos y campos obligatorios.
- Determinar `signed_effect` exclusivamente a partir de `event_type`.
- Persistir transacciones.
- Aplicar correcciones.
- Calcular el saldo.
- Generar reportes.
- Generar imágenes de reportes.
- Aplicar idempotencia.
- Exponer errores estructurados.

n8n debe limitarse a:

- Recibir eventos de Telegram.
- Mantener el estado conversacional.
- Presentar botones y solicitar datos.
- Enviar datos al backend.
- Interpretar respuestas.
- Mostrar mensajes al usuario.
- Manejar la UX de reintentos/cancelaciones.

---

# 4. API base

Base path:

```text
/api/v1
```

La API será privada y accesible únicamente desde la infraestructura autorizada.

No se contempla exposición pública directa del backend.

---

# 5. Endpoints v1

| Método | Endpoint | Responsabilidad |
|---|---|---|
| `GET` | `/health` | Health check técnico |
| `POST` | `/transactions` | Registrar una transacción |
| `POST` | `/transactions/{id}/corrections` | Corregir una transacción |
| `GET` | `/balance` | Obtener saldo bilateral |
| `GET` | `/reports/monthly` | Obtener reporte mensual |
| `GET` | `/reports/monthly/image` | Generar/obtener imagen del reporte mensual |

No se crean endpoints adicionales sin necesidad real.

---

# 6. Autenticación servicio-a-servicio

La opción v1 recomendada es una **API key interna dedicada al proyecto**.

Características:

- La clave vive únicamente en variables de entorno.
- No se almacena en el repositorio.
- n8n la envía mediante un header dedicado.
- Python valida la clave antes de ejecutar operaciones protegidas.
- La clave no será la contraseña de PostgreSQL.
- No se utilizarán credenciales administrativas de la infraestructura.

Header:

```text
X-API-Key: <internal-api-key>
```

En desarrollo local se utilizará una clave distinta a producción.

La API key es una credencial de servicio, no una identidad del usuario final.

---

# 7. Identidad del usuario

Telegram proporciona un `telegram_user_id`.

El backend recibe ese identificador y resuelve:

```text
telegram_user_id
        ↓
Python
        ↓
person_id
```

n8n **no** debe enviar directamente un `person_id` confiable.

Python mantiene la asociación controlada:

```text
telegram_user_id → Person
```

Esto evita que un workflow pueda falsificar la identidad de quien realizó la operación.

---

# 8. POST /transactions

## 8.1 Propósito

Registrar una nueva transacción.

El endpoint acepta **texto libre sin parsear** como contrato principal, y opcionalmente puede aceptar datos estructurados internos cuando sea útil para tests o integración controlada.

La regla principal es:

> Python es responsable de convertir `raw_text` en `amount` + `description`.

No se crea un endpoint `/parse` separado en v1.

---

## 8.2 Request

Ejemplo principal:

```json
{
  "telegram_user_id": "123456789",
  "event_type": "erick_gasta_para_mama",
  "raw_text": "S/ 35.50 taxi",
  "event_date": "2026-08-30",
  "idempotency_key": "telegram:123456789:update:987654321"
}
```

### Campos

| Campo | Tipo | Obligatorio | Responsable |
|---|---|---:|---|
| `telegram_user_id` | string | sí | n8n/Telegram |
| `event_type` | enum | sí | n8n mediante botón |
| `raw_text` | string | sí para flujo Telegram | Telegram/n8n |
| `event_date` | `YYYY-MM-DD` | sí | n8n |
| `idempotency_key` | string | sí | n8n/backend contract |

El backend resolverá internamente:

- `person_id`
- `amount`
- `description`
- `signed_effect`
- `recorded_at`

---

## 8.3 Event type

Los valores permitidos son exactamente:

```text
mama_entrega_dinero
erick_gasta_para_mama
erick_entrega_dinero
mama_devuelve
erick_devuelve
```

El backend rechaza cualquier valor fuera del enum.

El LLM **nunca** decide este campo.

---

# 9. Parsing

## 9.1 Flujo

```text
raw_text
   ↓
Parser determinístico
   ↓
¿Resultado válido?
   ├── Sí → continuar
   └── No → fallback LLM
                  ↓
             validación
                  ↓
               continuar
```

## 9.2 Parser determinístico

Primera opción:

- regex
- normalización de separadores
- reconocimiento de soles
- reconocimiento de decimales
- extracción de descripción

Ejemplo:

```text
"S/ 35.50 taxi"
```

produce conceptualmente:

```json
{
  "amount": "35.50",
  "description": "taxi"
}
```

## 9.3 Fallback LLM

El LLM únicamente puede devolver:

```json
{
  "amount": "35.50",
  "description": "taxi"
}
```

No puede devolver:

- `event_type`
- `person_id`
- `telegram_user_id`
- `signed_effect`
- `balance`
- autorización
- interpretación de deuda

El resultado del LLM siempre pasa por validación determinística antes de persistir.

---

# 10. Amount

Los montos se representan como strings decimales:

```json
{
  "amount": "35.50"
}
```

No se utilizan floats.

Reglas:

- moneda v1: **PEN / soles**
- se permiten céntimos
- monto positivo
- precisión monetaria definida por la capa de persistencia
- Python utiliza `Decimal`
- PostgreSQL utiliza `DECIMAL/NUMERIC`

---

# 11. Fecha

Se distinguen:

```text
event_date
recorded_at
```

### `event_date`

Fecha en que ocurrió el evento.

### `recorded_at`

Timestamp generado automáticamente por el backend al registrar la operación.

n8n puede solicitar:

- Hoy
- Ayer
- Otra fecha

Python valida siempre el valor final.

---

# 12. Cálculo del efecto financiero

El backend aplica una única función de dominio:

```text
event_type → signed_effect
```

Reglas v1:

| Event type | Efecto sobre S |
|---|---:|
| `mama_entrega_dinero` | `+amount` |
| `erick_gasta_para_mama` | `-amount` |
| `erick_entrega_dinero` | `-amount` |
| `mama_devuelve` | `-amount` |
| `erick_devuelve` | `+amount` |

Donde:

```text
S > 0 → Erick le debe a mamá
S < 0 → mamá le debe a Erick
S = 0 → no existe deuda neta
```

El backend calcula el saldo únicamente a partir de eventos `ACTIVE`.

---

# 13. GET /balance

Respuesta conceptual:

```json
{
  "balance": "30.00",
  "currency": "PEN",
  "direction": "erick_owes_mama"
}
```

## Enum de `direction`

Valores permitidos:

```text
erick_owes_mama
mama_owes_erick
no_debt
```

Regla:

```text
S > 0 → erick_owes_mama
S < 0 → mama_owes_erick
S = 0 → no_debt
```

`balance` representa la magnitud positiva de la deuda.

---

# 14. Correcciones

Endpoint:

```text
POST /api/v1/transactions/{id}/corrections
```

Una corrección puede reemplazar **el evento completo**, incluyendo:

- `event_type`
- `amount`
- `description`
- `event_date`

No se modifica destructivamente el evento original.

---

## 14.1 Cadena de correcciones

Una transacción puede ser corregida múltiples veces:

```text
A → B → C → ...
```

Cada corrección deja el evento anterior como:

```text
SUPERSEDED
```

El cálculo del saldo considera únicamente:

```text
status = ACTIVE
```

Por tanto, la cadena puede crecer sin límite práctico y el saldo no necesita recorrerla para determinar el estado actual.

---

## 14.2 Corrección de una transacción ya SUPERSEDED

Para evitar ramas ambiguas:

> Solo se puede corregir la versión actualmente `ACTIVE`.

Si se intenta corregir una transacción `SUPERSEDED`, el backend responde con error y obliga a corregir la versión activa más reciente.

Esto mantiene una única cadena lineal por transacción lógica.

---

# 15. Ventana temporal de correcciones

v1 **no impone una restricción técnica por mes**.

Un evento de cualquier fecha puede corregirse.

La expectativa operativa es revisar/corregir principalmente dentro del mes que está siendo auditado antes del cierre del reporte mensual, pero esto es una regla de uso, no un bloqueo técnico.

No existe todavía:

- cierre contable
- período bloqueado
- reapertura de período
- contabilidad formal

---

# 16. Idempotencia

La idempotencia es obligatoria.

Objetivo:

> Un mismo evento de entrada no debe crear dos transacciones por reintentos o duplicación del webhook.

El request contiene:

```text
idempotency_key
```

Ejemplo:

```text
telegram:123456789:update:987654321
```

La estrategia exacta de almacenamiento/constraint se definirá en la sección de persistencia, pero el contrato de API ya considera la clave como requisito.

---

# 17. Errores

La API utilizará errores estructurados.

Ejemplo:

```json
{
  "error": {
    "code": "INVALID_AMOUNT",
    "message": "The amount must be a positive decimal."
  }
}
```

Los códigos serán estables y aptos para que n8n pueda decidir la UX sin interpretar texto libre.

Ejemplos de códigos:

```text
UNAUTHORIZED
UNKNOWN_TELEGRAM_USER
INVALID_EVENT_TYPE
INVALID_AMOUNT
PARSER_FAILED
INVALID_EVENT_DATE
TRANSACTION_NOT_FOUND
TRANSACTION_NOT_ACTIVE
DUPLICATE_IDEMPOTENCY_KEY
VALIDATION_ERROR
INTERNAL_ERROR
```

No se utilizarán mensajes de error como contrato lógico.

---

# 18. Health check

Endpoint:

```text
GET /api/v1/health
```

Debe indicar al menos que el servicio está vivo.

La comprobación de dependencias puede ampliarse posteriormente si realmente se necesita un readiness check separado.

No se expone información sensible en la respuesta.

---

# 19. Reporte mensual

Endpoint:

```text
GET /api/v1/reports/monthly?year=2026&month=8
```

Python será responsable de:

1. consultar transacciones relevantes;
2. aplicar correcciones;
3. calcular saldo;
4. preparar resumen;
5. generar contenido del reporte;
6. generar la imagen.

n8n solamente distribuye el resultado por Telegram.

---

# 20. Imagen del reporte

Endpoint:

```text
GET /api/v1/reports/monthly/image?year=2026&month=8
```

La generación de la imagen ocurre en Python.

No se delega a n8n.

La tecnología concreta de generación gráfica se definirá durante implementación, manteniendo el principio:

```text
Python → genera imagen
n8n → entrega imagen por Telegram
```

---

# 21. Flujo completo de registro

```text
Telegram
   ↓
n8n Telegram Trigger
   ↓
n8n identifica estado conversacional
   ↓
Botón: event_type
   ↓
Usuario escribe monto + descripción
   ↓
Botones: fecha
   ↓
Confirmación
   ↓
n8n → POST /transactions
   ↓
Python
   ├── autentica request
   ├── resuelve Telegram user
   ├── parsea raw_text
   ├── fallback LLM si corresponde
   ├── valida resultado
   ├── calcula signed_effect
   ├── verifica idempotencia
   └── persiste
   ↓
Respuesta estructurada
   ↓
n8n
   ↓
Telegram
```

---

# 22. Estado conversacional

El estado multi-turno pertenece a **n8n**.

Ejemplo conceptual:

```text
telegram_user_id
    ↓
state = WAITING_FOR_AMOUNT
event_type = erick_gasta_para_mama
```

Python no será responsable de mantener el estado de la conversación de Telegram en v1.

Esto evita mezclar:

- estado de UX/orquestación
- estado del dominio financiero

El ciclo de vida y timeout concreto de las sesiones conversacionales queda como detalle de implementación del workflow n8n y deberá definirse antes de producción.

---

# 23. Seguridad

Reglas obligatorias:

- API privada.
- API key interna.
- PostgreSQL privado.
- Credenciales mediante variables de entorno.
- No credenciales en Git.
- No datos financieros reales en Git.
- No logs con secretos.
- No logs con datos financieros innecesarios.
- No aceptar `balance` desde n8n.
- No aceptar `signed_effect` desde n8n.
- No aceptar `signed_amount` desde n8n.
- No permitir que el LLM determine identidad o signo.
- Validación definitiva siempre en Python.

---

# 24. Responsabilidad de n8n frente a Python

### n8n puede

- controlar el flujo conversacional;
- mostrar botones;
- recopilar texto;
- recopilar fecha;
- solicitar confirmación;
- enviar requests;
- interpretar códigos de error;
- enviar respuestas a Telegram.

### n8n no puede

- calcular el saldo;
- decidir el signo financiero;
- decidir quién debe a quién;
- modificar el monto recibido para alterar el ledger;
- asignar arbitrariamente un `person_id`;
- confiar en el LLM para reglas financieras;
- persistir una segunda versión del ledger en paralelo.

---

# 25. Desarrollo vs. producción

## Desarrollo local

La implementación de Python y PostgreSQL se verificará localmente antes del deployment.

La decisión es mantener PostgreSQL como motor también en desarrollo, evitando SQLite→PostgreSQL.

Se recomienda un PostgreSQL local aislado para desarrollo/test.

No se utilizará la base de datos de producción para pruebas.

## Producción

```text
Telegram
   ↓ HTTPS
n8n.gonex.pe
   ↓ HTTP interno
Python
   ↓
PostgreSQL dedicado
```

El backend no requiere dominio público.

---

# 26. Contratos de pruebas

Antes de considerar estable la API se deben probar al menos:

### Happy path

- registro correcto;
- cálculo correcto;
- reporte mensual;
- generación de imagen.

### Validaciones

- monto inválido;
- monto cero;
- evento desconocido;
- fecha inválida;
- usuario Telegram desconocido;
- parser sin resultado.

### Seguridad

- API key incorrecta;
- ausencia de API key;
- intento de enviar `balance`;
- intento de enviar `signed_effect`;
- intento de falsificar `person_id`.

### Idempotencia

- mismo request dos veces;
- mismo `idempotency_key` con payload idéntico;
- conflicto de `idempotency_key`.

### Correcciones

- corrección de monto;
- corrección de descripción;
- corrección de fecha;
- corrección de `event_type`;
- múltiples correcciones;
- intento de corregir una versión `SUPERSEDED`.

---

# 27. Pendientes explícitos para secciones posteriores

No se resuelven aquí decisiones que pertenecen a otras partes del Technical Design:

1. Esquema SQL definitivo.
2. Constraint exacta de idempotencia.
3. Índices.
4. Migraciones.
5. Implementación concreta del parser.
6. Implementación del fallback LLM.
7. Modelo exacto de sesión/timeout dentro de n8n.
8. Formato definitivo del reporte.
9. Tecnología concreta de generación de imagen.
10. Estrategia de backup/restore.
11. Dockerfile.
12. Docker Compose del proyecto.
13. CI/CD.
14. Estrategia definitiva de logging/observabilidad.
15. Decisión futura sobre expansión de más de dos personas.
16. Campo/rol adicional de `Person` solo si aparece una necesidad real.

---

# 28. Principios de implementación para los agentes

Codex y Claude Code deben tratar este documento como contrato.

Regla:

> Si una implementación entra en conflicto con este documento, el agente no debe inventar una nueva regla silenciosamente. Debe señalar el conflicto y solicitar decisión humana.

Prioridades:

1. Integridad del ledger.
2. Seguridad.
3. Idempotencia.
4. Trazabilidad.
5. Simplicidad.
6. UX.

---

# 29. Estado

**2.5 se considera cerrada.**

El siguiente paso es:

**2.6 — Security, Reliability & Operational Design**
