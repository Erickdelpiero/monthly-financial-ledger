# PHASE 2.10 — TELEGRAM ↔ n8n UX & CONVERSATIONAL FLOW

**Proyecto:** Personal Expense Ledger — Telegram + n8n + Python + PostgreSQL
**Fase:** 2 — Technical Design
**Sección:** 2.10 — Flujo Telegram ↔ n8n: estados, botones y UX (registro y corrección)
**Estado:** CERRADO — validado por revisión cruzada
**Fecha:** 2026-08-31

---

## 1. Propósito

Definir exclusivamente el comportamiento de la interfaz conversacional de Telegram y la orquestación temporal en n8n, cubriendo tanto el **registro de una transacción nueva** como la **corrección de una transacción existente**.

Este documento no redefine:

* reglas financieras;
* modelo de datos;
* API;
* parser;
* LLM;
* ledger;
* persistencia;
* reportes;
* CI/CD;
* seguridad.

Esos aspectos ya están definidos en las secciones correspondientes de la Fase 2.

Principio:

> **Telegram presenta; n8n orquesta; Python decide; PostgreSQL persiste.**

---

# 2. Decisiones heredadas

Se consideran cerradas las siguientes decisiones:

1. Telegram es la interfaz del MVP.
2. Telegram utiliza webhook HTTPS.
3. El webhook llega a la instancia n8n existente (`gonex-n8n`).
4. n8n es responsable del estado conversacional temporal.
5. Python no mantiene sesiones conversacionales de Telegram.
6. Python es la fuente única de verdad del dominio financiero.
7. n8n no implementa lógica financiera.
8. `event_type` se selecciona mediante opciones predefinidas.
9. El usuario introduce monto y descripción mediante texto.
10. La fecha se selecciona mediante opciones de Telegram.
11. El registro definitivo requiere confirmación explícita del usuario.
12. Las respuestas de confirmación utilizan templates fijos.
13. El LLM no genera los mensajes de UX.
14. Los errores del backend llegan a n8n mediante códigos estructurados, alineados exactamente con el listado oficial de 2.5 (ver §21).
15. Una transacción solamente se considera registrada después de una persistencia exitosa en Python/PostgreSQL.
16. Una corrección solamente se considera aplicada después de una respuesta exitosa de `POST /transactions/{id}/corrections`.
17. Una corrección no puede aplicarse sobre una transacción ya `SUPERSEDED` (el backend la rechaza; ver 2.3/2.5).

La infraestructura real confirma:

```text
Telegram
   ↓ HTTPS
n8n.gonex.pe
   ↓
n8n
```

n8n utiliza actualmente:

```text
N8N_PROTOCOL=https
WEBHOOK_URL=https://n8n.gonex.pe/
GENERIC_TIMEZONE=America/Lima
```

La instancia existente será reutilizada inicialmente.

---

# 3. Objetivo de UX

La interfaz debe ser:

* extremadamente simple;
* fácil de entender;
* predecible;
* basada en botones siempre que sea posible;
* sin lenguaje técnico;
* sin depender de que el usuario conozca cómo funciona el sistema;
* difícil de confirmar accidentalmente.

El diseño debe priorizar:

> **menos opciones, menos texto y menos posibilidades de equivocación.**

No se busca crear un chatbot generalista. Este principio se aplica tanto al registro como a la corrección.

---

# 4. Flujo principal — Registro

```text
INICIO
  ↓
Seleccionar tipo de operación
  ↓
Ingresar monto + descripción
  ↓
Seleccionar fecha
  ↓
Mostrar resumen
  ↓
¿Confirmar?
  ├── Sí → POST /transactions → registrar
  └── No → cancelar / volver a iniciar
```

La transacción **no se envía a FastAPI antes de la confirmación final**.

```text
Estado conversacional
        ↓
   NO ES LEDGER
        ↓
Confirmación
        ↓
POST /transactions
        ↓
Persistencia
```

---

# 5. Estado conversacional

n8n mantiene temporalmente una sesión asociada al usuario de Telegram.

El estado conceptual mínimo es:

```text
telegram_user_id
current_step
selected_event_type
pending_raw_text
pending_event_date
pending_idempotency_key
pending_correction_target_id   ← solo aplica al flujo de corrección
created_at
expires_at
```

Este estado representa una operación pendiente (registro o corrección). No representa una transacción financiera registrada ni una corrección aplicada.

---

# 6. Estados permitidos — Registro

### `IDLE`
No existe una operación pendiente.

### `WAITING_EVENT_TYPE`
El sistema espera que el usuario seleccione qué ocurrió.

### `WAITING_TRANSACTION_TEXT`
El sistema espera monto + descripción.

### `WAITING_DATE`
El sistema espera la fecha del evento.

### `WAITING_CONFIRMATION`
El sistema muestra el resumen y espera `CONFIRMAR` / `CANCELAR`.

### `PROCESSING`
El usuario confirmó y n8n está realizando la llamada a Python. **Este estado está exento del timeout de inactividad** (ver §19): la sesión no espera al usuario, espera al backend, y expirarla aquí podría hacer creer al usuario que una operación exitosa falló, generando un duplicado real.

### `COMPLETED`
La operación fue persistida correctamente y se comunica el resultado.

### `CANCELLED`
La operación pendiente fue descartada.

---

# 7. Estados permitidos — Corrección

### `WAITING_CORRECTION_SELECTION`
El sistema presenta las últimas 3–5 transacciones `ACTIVE` del usuario y espera que seleccione cuál corregir.

### `WAITING_CORRECTION_EVENT_TYPE`
El sistema pregunta si el tipo de operación también debe cambiar, o si se mantiene el original.

### `WAITING_CORRECTION_TEXT`
El sistema espera el monto/descripción corregidos.

### `WAITING_CORRECTION_DATE`
El sistema espera la fecha corregida (o confirmación de que se mantiene la original).

### `WAITING_CORRECTION_CONFIRMATION`
El sistema muestra un resumen **comparativo** (valor original vs. valor corregido) y espera `CONFIRMAR` / `CANCELAR`.

### `PROCESSING_CORRECTION`
n8n llama a `POST /transactions/{id}/corrections`. Exento del timeout, igual que `PROCESSING`.

### `CORRECTION_COMPLETED`
La corrección fue aplicada; el evento original quedó `SUPERSEDED` y el nuevo `ACTIVE`.

### `CORRECTION_CANCELLED`
La corrección pendiente fue descartada; la transacción original permanece sin cambios.

---

# 8. Inicio del registro

```text
¿Qué ocurrió?

[ Mamá me entregó dinero ]
[ Yo gasté para mamá ]
[ Yo le entregué dinero ]
[ Mamá me devolvió dinero ]
[ Yo le devolví dinero ]
```

Los textos finales de los botones pueden optimizarse durante implementación, pero deben corresponder exactamente a los `event_type` definidos por el contrato de API. n8n no debe inferir ni modificar el significado financiero del botón.

---

# 9. Selección de `event_type` (registro)

```text
telegram_user_id = X
current_step = WAITING_TRANSACTION_TEXT
selected_event_type = erick_gasta_para_mama
```

El usuario no debe escribir manualmente el `event_type`.

---

# 10. Ingreso de monto y descripción

```text
¿Cuánto fue y en qué?

Ejemplo:
S/ 35.50 taxi
```

El texto se conserva como `pending_raw_text`. n8n no intenta determinar monto, descripción, signo o saldo — el parsing corresponde a Python.

---

# 11. Selección de fecha

```text
¿De qué fecha fue?

[ Hoy ]
[ Ayer ]
[ Otra fecha ]
[ Cancelar ]
```

`Hoy`/`Ayer` se calculan respecto a `America/Lima`. Para una fecha distinta se utilizará un mecanismo de selección compatible con Telegram/n8n definido durante implementación. Python siempre vuelve a validar la fecha recibida.

---

# 12. Resumen antes de confirmar (registro)

```text
Revisa tu registro:

Yo gasté para mamá
S/ 35.50
Taxi
30 de agosto

¿Está correcto?

[ CONFIRMAR ]
[ CANCELAR ]
```

No debe mostrar `event_type` interno, `signed_effect`, `person_id`, `idempotency_key`, IDs internos ni información técnica.

---

# 13. Confirmación explícita (registro)

Solo tras `CONFIRMAR`, n8n ejecuta `POST /api/v1/transactions`. Antes de ese momento no existe una transacción financiera registrada. Si el usuario selecciona `CANCELAR`, la sesión pasa a `CANCELLED` y no se llama al backend.

---

# 14. Idempotency key (registro)

La `idempotency_key` se genera **antes de la confirmación**, cuando la operación pendiente queda suficientemente definida:

```text
Inicio de operación
       ↓
generar idempotency_key
       ↓
guardar en estado n8n
       ↓
recopilar datos
       ↓
confirmación
       ↓
POST /transactions
       ↓
misma idempotency_key
```

Un doble envío o reintento de la misma confirmación reutiliza la misma clave. La protección definitiva contra duplicados pertenece al `UNIQUE` de PostgreSQL (2.6).

---

# 15. Doble pulsación / reintento de confirmación

Mientras el request está en `PROCESSING`, el workflow no debe aceptar una segunda confirmación como una nueva operación. Un reintento de transporte debe reutilizar `pending_idempotency_key`, nunca generar una nueva.

---

# 16. Resultado exitoso (registro)

```text
✓ Registrado

Yo gasté para mamá
S/ 35.50 — Taxi

Saldo actualizado:
Erick le debe S/ 148.20 a mamá.
```

El saldo mostrado es el **saldo acumulado tras aplicar esta transacción sobre el saldo previo**, no el monto de la transacción en sí — debe quedar claro en el template real que ambos valores pueden diferir. El texto exacto se definirá como template fijo; no se utiliza LLM para generar esta respuesta.

---

# 17. Notificación al otro usuario (registro)

```text
Erick registró:

S/ 35.50
Taxi

Como gasto para mamá.

Ahora no necesitas registrarlo nuevamente.
```

Se envía únicamente después de que Python confirme la persistencia exitosa. Un fallo posterior de Telegram no revierte ni modifica el ledger.

---

# 18. Flujo de corrección de transacciones

## 18.1 Inicio

El usuario accede mediante un comando/botón explícito (ej. `/corregir` o botón persistente "Corregir un registro").

```text
Estos son tus últimos registros:

1. 30 ago — S/ 35.50 — Taxi (gasto para mamá)
2. 29 ago — S/ 100.00 — Entrega de mamá
3. 27 ago — S/ 12.90 — Farmacia (gasto para mamá)

¿Cuál deseas corregir?

[ 1 ]  [ 2 ]  [ 3 ]  [ Cancelar ]
```

Solo se listan transacciones con `status = ACTIVE` y pertenecientes al usuario que inició la corrección (o, si se decide permitir corregir registros del otro usuario, esto debe quedar como decisión explícita separada — v1 asume que cada usuario corrige únicamente lo que él mismo registró, salvo que Erick indique lo contrario).

## 18.2 Selección de qué cambia

```text
Vas a corregir:
30 ago — S/ 35.50 — Taxi

¿Qué deseas corregir?

[ El tipo de operación ]
[ El monto/descripción ]
[ La fecha ]
[ Todo ]
[ Cancelar ]
```

Según la selección, n8n recorre únicamente los pasos necesarios (`WAITING_CORRECTION_EVENT_TYPE`, `WAITING_CORRECTION_TEXT`, `WAITING_CORRECTION_DATE`), reutilizando los mismos botones/prompts ya definidos en §8–§11 para el flujo de registro. Los campos no tocados conservan el valor original.

## 18.3 Resumen comparativo antes de confirmar

```text
Revisa la corrección:

Antes:
Yo gasté para mamá — S/ 35.50 — Taxi — 30 ago

Después:
Yo gasté para mamá — S/ 40.00 — Taxi — 30 ago

¿Confirmas la corrección?

[ CONFIRMAR ]
[ CANCELAR ]
```

El formato comparativo (antes/después) es obligatorio — un resumen que solo muestre el valor nuevo no permite verificar que la corrección captura la intención real del usuario, especialmente relevante dado que uno de los usuarios no domina bien la tecnología.

## 18.4 Confirmación y llamada al backend

Solo tras `CONFIRMAR`, n8n ejecuta `POST /transactions/{id}/corrections`. La `idempotency_key` de la corrección se genera con el mismo criterio que en el registro (§14): antes de la confirmación, reutilizada en reintentos.

## 18.5 Resultado

```text
✓ Corrección aplicada

30 ago — Taxi
S/ 35.50 → S/ 40.00

Saldo actualizado:
Erick le debe S/ 152.70 a mamá.
```

## 18.6 Notificación de corrección al otro usuario

```text
Erick corrigió un registro:

30 ago — Taxi
S/ 35.50 → S/ 40.00

El saldo se actualizó.
```

Se envía con el mismo criterio que la notificación de registro (§17): solo tras persistencia exitosa, nunca antes.

## 18.7 Corrección sobre transacción ya superseded

Si el backend rechaza la corrección porque la transacción ya fue corregida por otra (`TRANSACTION_NOT_ACTIVE`, ver §21), n8n debe mostrar:

```text
Este registro ya fue corregido anteriormente.

Puedes corregir la versión más reciente.

[ VER REGISTRO ACTUAL ]
[ CANCELAR ]
```

No se debe intentar resolver automáticamente la cadena de correcciones — la resolución hacia el evento activo correspondiente es responsabilidad del backend (2.3), no de n8n.

---

# 19. Abandono y timeout

Timeout de sesión conversacional: **30 minutos** de inactividad.

```text
session → expired
```

**Excepción explícita:** los estados `PROCESSING` y `PROCESSING_CORRECTION` no cuentan como "inactividad del usuario" — están esperando al backend, no al usuario, y no deben expirar por este mecanismo. Si `PROCESSING` se extendiera de forma anómala, corresponde a un timeout HTTP de la llamada a Python (ver §21), no al timeout de sesión conversacional.

Una sesión expirada no afecta al ledger porque el estado pendiente todavía no representa una transacción registrada ni una corrección aplicada. Si el usuario vuelve después del timeout, debe iniciar una nueva operación.

---

# 20. Nueva operación durante una sesión pendiente

```text
Tienes un registro pendiente.

[ CONTINUAR ]
[ CANCELAR Y EMPEZAR NUEVO ]
```

Aplica tanto si la sesión pendiente es de registro como de corrección. No se deben combinar silenciosamente datos de dos operaciones distintas.

---

# 21. Errores del backend

n8n utiliza los códigos estructurados definidos formalmente en 2.5. Este documento no introduce códigos nuevos fuera de esa lista; los siguientes son los relevantes para el flujo conversacional:

```text
INVALID_REQUEST
INVALID_EVENT_TYPE
INVALID_AMOUNT
INVALID_DATE
UNAUTHORIZED_USER
DUPLICATE_REQUEST
TRANSACTION_NOT_FOUND
INVALID_CORRECTION
TRANSACTION_NOT_ACTIVE
DATABASE_ERROR
LLM_FALLBACK_ERROR
INTERNAL_ERROR
```

n8n convierte estos códigos en mensajes amigables. Ejemplo:

```text
No pude entender el monto.

Escribe algo como:
S/ 35.50 taxi

[ REINTENTAR ]
[ CANCELAR ]
```

No se muestra al usuario stack trace, JSON interno, mensajes técnicos, nombres de tablas, excepciones ni credenciales.

---

# 22. Fallo de comunicación con Python

Si n8n no logra comunicarse con FastAPI (timeout/error), el workflow **no debe asumir que la operación fue registrada o corregida**. Debe conservar el contexto necesario para un reintento controlado usando la misma `idempotency_key`.

```text
No pude confirmar el registro todavía.

Puedes intentar nuevamente.
```

No debe afirmarse "Registrado" ni "Corregido" hasta recibir confirmación exitosa del backend.

---

# 23. Fallo posterior de Telegram

Telegram es un canal de entrega, no una fuente de verdad del ledger. Si la transacción/corrección ya fue persistida correctamente pero falla el envío del mensaje de confirmación o de la notificación, la transacción permanece registrada/corregida tal cual. No se reintenta creando una nueva operación.

---

# 24. Principio de no duplicación

```text
n8n state
    ≠
financial ledger
```

n8n puede tener una operación pendiente (registro o corrección) pero nunca una copia paralela del ledger. La única fuente de verdad financiera es PostgreSQL a través del backend Python.

---

# 25. Flujo completo definitivo — Registro

```text
┌──────────────┐
│   Telegram   │
└──────┬───────┘
       ▼
┌──────────────┐
│     n8n      │
│ Conversation │
│    State     │
└──────┬───────┘
       ├── event_type
       ├── raw_text
       ├── event_date
       ├── confirmation
       ▼
┌──────────────────┐
│ POST /transactions│
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Python / FastAPI │
│ validate          │
│ resolve identity  │
│ parse              │
│ calculate effect  │
│ persist            │
└────────┬─────────┘
         ▼
┌──────────────────┐
│   PostgreSQL     │
│      Ledger      │
└────────┬─────────┘
         ▼
┌──────────────┐
│     n8n      │
├── confirmación al usuario
└── notificación al otro usuario
```

## Flujo completo definitivo — Corrección

```text
┌──────────────┐
│   Telegram   │
└──────┬───────┘
       ▼
┌──────────────────────┐
│         n8n           │
│ Lista transacciones   │
│ ACTIVE del usuario     │
└──────┬────────────────┘
       ├── selección de transacción
       ├── campos a corregir
       ├── nuevos valores
       ├── resumen comparativo
       ├── confirmation
       ▼
┌────────────────────────────────┐
│ POST /transactions/{id}/       │
│ corrections                    │
└────────┬────────────────────────┘
         ▼
┌──────────────────┐
│ Python / FastAPI │
│ validate original │
│ mark SUPERSEDED   │
│ create correction │
│ recalculate balance│
└────────┬─────────┘
         ▼
┌──────────────────┐
│   PostgreSQL     │
│      Ledger      │
└────────┬─────────┘
         ▼
┌──────────────┐
│     n8n      │
├── confirmación al usuario
└── notificación al otro usuario
```

---

# 26. Reglas de UX no negociables

### n8n debe

* usar botones cuando la opción sea cerrada;
* mantener el estado temporal (registro y corrección);
* pedir confirmación antes de registrar o corregir;
* mostrar resumen comparativo (antes/después) en correcciones;
* evitar duplicar solicitudes durante `PROCESSING`/`PROCESSING_CORRECTION`;
* conservar la `idempotency_key` durante el intento;
* presentar errores de forma amigable;
* notificar al otro usuario después de persistencia/corrección exitosa;
* excluir `PROCESSING`/`PROCESSING_CORRECTION` del timeout de inactividad.

### n8n no debe

* calcular saldo;
* calcular `signed_effect`;
* decidir quién debe a quién;
* modificar montos;
* modificar el significado de `event_type`;
* persistir transacciones o correcciones directamente;
* almacenar una copia paralela del ledger;
* resolver automáticamente cadenas de corrección;
* usar un LLM para generar decisiones financieras;
* confirmar un registro/corrección sin respuesta exitosa de Python.

---

# 27. Alcance del MVP

Diseñado para 2 usuarios (Erick y mamá). No se diseña una UX genérica para múltiples participantes. Si posteriormente se amplía el número de personas, se revisará la UX en ese momento.

---

# 28. Decisiones deliberadamente no introducidas

* chatbot generalista;
* NLG para mensajes;
* comandos complejos;
* menús profundos;
* dashboards dentro de Telegram;
* categorización avanzada;
* autenticación adicional del usuario final;
* rate limiting complejo;
* recuperación sofisticada de sesiones;
* infraestructura adicional de mensajería;
* corrección de registros ajenos sin decisión explícita (ver §18.1).

---

# 29. Pendientes de implementación

1. mecanismo exacto de almacenamiento temporal del estado en n8n;
2. implementación concreta del timeout de 30 minutos (y su exclusión en estados `PROCESSING*`);
3. nombres definitivos de los nodos/workflows;
4. textos finales de los templates (registro y corrección);
5. formato concreto de selección de fecha;
6. mecanismo concreto para generar la `idempotency_key`;
7. manejo técnico de reintentos HTTP;
8. mecanismo concreto para enviar la notificación al segundo usuario;
9. decisión final sobre si un usuario puede corregir registros del otro (por defecto: no, salvo indicación contraria).

Estos detalles no pueden modificar las reglas funcionales de este documento.

---

# 30. Nota de consistencia retroactiva

Los diagramas de flujo en 2.4 (Application Integration) y 2.7 (Deployment/Runtime) no muestran explícitamente el paso de confirmación (`WAITING_CONFIRMATION` → `CONFIRMAR`) descrito aquí. Este documento (2.10) es la referencia autoritativa vigente sobre el flujo conversacional completo; se recomienda una actualización menor de los diagramas de 2.4/2.7 para incluir ese paso, sin que ello implique reabrir ninguna decisión ya cerrada en esas secciones.

---

# 31. Evidencia de infraestructura utilizada

```text
n8n container:      gonex-n8n
Image:               n8nio/n8n:latest
Network:              docker_gonex-network
n8n URL:              https://n8n.gonex.pe/
Timezone:             America/Lima
Persistent volume:    docker_n8n-data
Host port:            5678
```

```text
Internet
   ↓
HTTPS :443
   ↓
Nginx
   ↓
localhost:5678
   ↓
gonex-n8n
```

Este documento no introduce una nueva instancia de n8n ni una nueva capa de reverse proxy.

---

## Estado

**2.10 — CERRADO.**

Siguiente documento: **2.11 — Security + Secrets** (consolidación de decisiones ya tomadas en 2.6 y 2.7).
