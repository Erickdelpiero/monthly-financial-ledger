# FASE 2 — Technical Design
## 2.3 — Data Model & Ledger Design

**Proyecto:** Bot personal de control de flujos de dinero — Usuario A ↔ Usuario B  
**Versión:** 1.1 — Propuesta consolidada tras revisión cruzada  
**Estado:** Draft técnico-conceptual aprobado para avanzar a 2.4

> **Privacidad:** Este documento está destinado a un repositorio público. No contiene nombres reales, identificadores de Telegram, saldos, transacciones, capturas ni otros datos financieros reales. Los ejemplos son sintéticos.

---

## 1. Objetivo del modelo

El sistema no modela una billetera, cuenta bancaria ni recorrido físico del dinero. Mantiene una **cuenta corriente bilateral** entre dos personas y determina quién debe a quién y cuánto.

El modelo debe registrar movimientos, conservar trazabilidad, permitir correcciones sin sobrescribir evidencia, calcular el saldo determinísticamente y permitir auditoría mensual.

---

## 2. Alcance matemático de v1

La relación financiera de v1 es **deliberadamente bilateral**.

Aunque `Person` sea una entidad independiente por limpieza del modelo, el cálculo actual no está diseñado para N personas. Una futura ampliación requeriría rediseñar la representación matemática del saldo, por ejemplo mediante saldos por pareja.

> **v1 = una relación financiera bilateral entre dos personas.**

---

## 3. Principio fundamental: Ledger como fuente de verdad

El saldo no se almacena como un valor editable.

```text
Saldo actual = Σ efecto_financiero(eventos ACTIVE)
```

El ledger es la fuente de verdad; el saldo es un valor derivado.

Las correcciones nunca consisten en editar manualmente el saldo.

---

## 4. Convención matemática del saldo

Se establece una única definición:

> **S > 0 → Usuario A le debe dinero a Usuario B.**  
> **S < 0 → Usuario B le debe dinero a Usuario A.**  
> **S = 0 → No existe deuda neta.**

Esta convención debe ser idéntica en Python, SQL, reportes, Telegram, tests y documentación.

---

## 5. Tipos de evento

| Código | Descripción | Efecto sobre S |
|---|---|---:|
| `B_ENTREGA_DINERO` | Usuario B entrega dinero a Usuario A | `+monto` |
| `A_GASTA_PARA_B` | Usuario A realiza un gasto para Usuario B | `-monto` |
| `A_ENTREGA_DINERO` | Usuario A entrega dinero a Usuario B | `-monto` |
| `B_DEVUELVE` | Usuario B devuelve dinero a Usuario A | `-monto` |
| `A_DEVUELVE` | Usuario A devuelve dinero a Usuario B | `+monto` |

La semántica y los signos no podrán cambiarse sin una decisión explícita.

---

## 6. El ledger no rastrea físicamente el dinero

El sistema no intentará determinar de dónde salió físicamente cada sol.

Por ejemplo:

```text
Usuario B entrega S/100
↓
Usuario A gasta S/70 para B
↓
Saldo pendiente = S/30
↓
Usuario A posteriormente paga otro gasto de B con su tarjeta
```

No es necesario saber qué dinero físico se utilizó.

V1 no tendrá:

- Entidad "billetera".
- Tracking de efectivo.
- Conciliación bancaria.
- Integración automática con Yape/Plin.
- Asociación física entre dinero recibido y gastos posteriores.

Una captura de Yape/Plin puede ser evidencia proporcionada por el usuario, pero no fuente automática de movimientos.

---

## 7. Modelo de entidades

La primera versión utilizará dos entidades principales:

```text
Person
Transaction
```

Las correcciones se modelan mediante relaciones entre `Transaction`.

No se crearán entidades adicionales hasta que exista una necesidad real.

### 7.1 Person

| Campo | Tipo conceptual | Descripción |
|---|---|---|
| `id` | UUID / identificador | Identificador interno |
| `telegram_user_id` | identificador | Identificador único de Telegram |
| `name` | texto | Nombre visible |
| `is_active` | boolean | Permite desactivar una persona |
| `created_at` | timestamp | Fecha de creación |

Se elimina `Person.role` de v1 por no existir una necesidad funcional actual.

En v1 existirán exactamente dos personas, pero la identidad se almacenará como datos y no se codificará dentro de la lógica financiera.

### 7.2 Transaction

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID | Identificador único |
| `event_type` | enum | Uno de los cinco tipos definidos |
| `amount` | DECIMAL / NUMERIC | Monto positivo con céntimos |
| `description` | TEXT | Descripción del movimiento |
| `event_date` | DATE | Fecha en que ocurrió |
| `registered_at` | TIMESTAMP | Momento de registro |
| `created_by` | FK → Person | Persona que registró |
| `status` | enum | Estado del evento |
| `superseded_by` | FK nullable → Transaction | Evento que lo reemplaza |
| `source_reference` | TEXT nullable | Referencia para idempotencia/trazabilidad |
| `created_at` | TIMESTAMP | Timestamp técnico |

`source_reference` queda reservado para el mecanismo concreto de idempotencia que se definirá posteriormente.

---

## 8. Montos

La moneda será exclusivamente:

```text
PEN — Sol peruano
```

Se aceptan céntimos.

No se utilizará `float` para representar dinero.

```text
PostgreSQL → NUMERIC / DECIMAL
Python → Decimal
```

---

## 9. Signo financiero y event_type

El signo no será introducido manualmente por el usuario ni por el LLM.

Existirá una única función determinística equivalente a:

```text
event_type → signed_effect
```

Ejemplo:

```text
B_ENTREGA_DINERO
→ +amount

A_GASTA_PARA_B
→ -amount
```

La lógica financiera debe existir en un único punto de la aplicación.

---

## 10. Fecha del evento vs. fecha de registro

Se diferencian:

### `event_date`
Cuándo ocurrió realmente el movimiento.

### `registered_at`
Cuándo fue introducido al sistema.

Esto permite registrar posteriormente un gasto sin perder trazabilidad temporal.

---

## 11. Estado de una transacción

Una transacción no se elimina físicamente.

```text
ACTIVE
SUPERSEDED
```

`ACTIVE` participa en el saldo.

`SUPERSEDED` fue reemplazada por una corrección y conserva su historial.

---

## 12. Corrección de errores

Se utiliza **soft correction / supersession**.

Una corrección reemplaza el evento completo, no solamente el monto. Puede modificar, cuando corresponda:

- `event_type`
- `amount`
- `description`
- `event_date`
- otros campos propios del evento que sean corregibles

Ejemplo:

```text
Transaction A
S/50
"Gasto supermercado"
```

Si el valor correcto es S/55:

```text
Transaction B
S/55
"Gasto supermercado"
```

Y:

```text
A.status = SUPERSEDED
A.superseded_by = B
B.status = ACTIVE
```

El evento original no se modifica ni elimina.

---

## 13. Correcciones encadenadas

Las correcciones pueden encadenarse:

```text
A → B → C
```

El saldo siempre considera únicamente los eventos `ACTIVE`.

Por ejemplo:

```text
A = SUPERSEDED
B = SUPERSEDED
C = ACTIVE
```

El saldo considera C.

La cadena histórica permite reconstruir la evolución de la corrección y no existe un límite artificial al número de correcciones.

---

## 14. Restricción temporal de correcciones

En v1 **no existe una restricción técnica de ventana temporal**.

La expectativa funcional es realizar la mayoría de correcciones durante la revisión mensual, pero esto es una práctica de uso, no una regla técnica.

Por tanto, técnicamente puede corregirse un evento antiguo.

El bloqueo formal de períodos cerrados, si posteriormente resulta necesario, será una funcionalidad futura explícita.

---

## 15. Identificación del usuario

El usuario que registra una operación será determinado por Telegram:

```text
Telegram user_id
        ↓
Person
        ↓
created_by
```

El LLM no puede decidir quién realizó la operación.

---

## 16. Tipo de evento y UI

El tipo de evento tampoco será determinado inicialmente por el LLM.

El usuario seleccionará una acción mediante botones:

```text
[Mamá me dio dinero]
[Gasté para mamá]
[Le devolví a mamá]
[Mamá me devolvió]
```

Los textos anteriores son ejemplos de interfaz y no deben incorporarse literalmente a documentación pública con nombres reales; la implementación pública utilizará nomenclatura genérica cuando corresponda.

Flujo:

```text
Telegram UI
    ↓
event_type determinado
    ↓
texto libre
    ↓
parser determinístico
    ↓
amount + description
    ↓
ledger
```

---

## 17. Parser y NLU

El parser determinístico será el mecanismo principal.

Ejemplo sintético:

```text
"50.50 pan y leche"
```

produce:

```text
amount = 50.50
description = "pan y leche"
```

El LLM no participa en el camino feliz.

Si el parser no puede extraer un monto válido:

```text
Parser
  ↓
¿Puede interpretar?
  ├── Sí → continuar
  └── No → NLU fallback
```

El LLM solamente podrá devolver información equivalente a:

```json
{
  "amount": 50.50,
  "description": "pan y leche"
}
```

No podrá determinar:

```text
event_type
payer
receiver
signed_amount
balance
```

---

## 18. Validaciones antes de persistir

Antes de insertar una transacción:

```text
event_type válido
+
amount > 0
+
amount representable con céntimos
+
description válida
+
event_date válida
+
created_by válido
```

Si falla una validación:

```text
NO escribir en DB
```

La respuesta al usuario será mediante template fijo.

---

## 19. Idempotencia y duplicados

Telegram/n8n pueden potencialmente reenviar eventos.

El sistema deberá contar con un mecanismo de idempotencia para impedir registros técnicos duplicados.

`source_reference` se reserva para almacenar la referencia necesaria.

La solución concreta se definirá en el diseño de persistencia e integración con n8n.

No se utilizarán heurísticas como:

```text
monto + descripción + fecha
```

para deducir duplicados.

---

## 20. Integridad del ledger

La base de datos deberá proteger, en la medida razonable para v1:

- Montos positivos.
- Tipos de evento válidos.
- Relaciones válidas.
- Estados válidos.
- Correcciones coherentes.
- Identificadores únicos.
- Integridad referencial.

Las reglas financieras críticas deberán estar cubiertas por Python y, cuando sea razonable, por restricciones de PostgreSQL.

---

## 21. Ejemplo completo

```text
Movimiento 1:
Usuario B entrega S/100 a Usuario A
→ S = +100

Movimiento 2:
Usuario A gasta S/70 para Usuario B
→ S = +30

Movimiento 3:
Usuario A gasta S/40 para Usuario B
→ S = -10
```

Resultado:

> Usuario B debe S/10 a Usuario A.

El sistema no necesita conocer el medio físico utilizado.

---

## 22. Reportes derivados del ledger

Los reportes semanales y mensuales no serán otra fuente de verdad.

Se generan consultando el ledger.

### Reporte semanal

Debe determinar:

```text
saldo actual
quién debe a quién
monto
```

### Reporte mensual

Debe mostrar como mínimo:

```text
fecha del evento
hora de registro
tipo de movimiento
monto
descripción
```

y el resultado acumulado del período.

---

## 23. Privacidad y repositorio público

El repositorio será público.

Los datos reales del ledger **nunca** forman parte del repositorio Git.

No se permitirá subir:

- Gastos reales.
- Saldos reales.
- Descripciones reales.
- Capturas reales de Yape/Plin.
- IDs privados de Telegram.
- Credenciales.
- Tokens.
- Variables de entorno reales.
- Reportes generados con datos reales.

Los tests utilizarán exclusivamente datos sintéticos.

Esta regla prevalece sobre el patrón existente en `monthly-sop-automation`, donde `output/` se utiliza como evidencia versionada.

---

## 24. Base de datos

La persistencia de producción utilizará PostgreSQL sobre la instancia existente:

```text
gonex-postgres
```

El proyecto tendrá:

```text
Base de datos propia
+
rol/usuario propio
+
credenciales de mínimo privilegio
```

No se utilizarán credenciales administrativas de PostgreSQL/n8n.

Conceptualmente:

```text
gonex-postgres
│
├── n8n database
├── otras bases existentes
└── personal_finance database
       └── dedicated role
```

Los nombres definitivos se decidirán durante la implementación.

---

## 25. Evolución futura

Podrían agregarse posteriormente:

- Más personas.
- Categorías.
- Adjuntos/evidencias.
- Métodos de pago.
- Etiquetas.
- Períodos contables.
- Auditoría avanzada.
- Integraciones externas.

Pero ninguna se incorporará a v1 sin necesidad concreta.

Agregar una tercera persona requerirá revisar y posiblemente rediseñar la lógica matemática del saldo.

---

## 26. Principios de diseño fijados

- **P1 — Ledger primero:** fuente de verdad.
- **P2 — Saldo derivado:** nunca se edita directamente.
- **P3 — Dinero determinístico:** Python `Decimal` + PostgreSQL `NUMERIC`.
- **P4 — Tipo cerrado:** la UI determina el evento; el LLM no.
- **P5 — NLU limitado:** fallback de extracción únicamente.
- **P6 — Sin NLG financiero:** respuestas mediante templates.
- **P7 — Historial preservado:** correcciones mediante nuevos eventos.
- **P8 — Corrección completa:** puede cambiar tipo y fecha.
- **P9 — Sin tracking físico:** obligaciones económicas, no movimiento físico.
- **P10 — Privacidad por diseño:** datos reales nunca al repositorio público.
- **P11 — Bilateral en v1:** el cálculo representa una relación entre dos personas.
- **P12 — Minimalismo:** no agregar abstracciones sin necesidad.

---

## 27. Decisiones pendientes para las siguientes secciones

1. Esquema SQL definitivo.
2. Nombres definitivos de tablas y columnas.
3. UUID vs. otro mecanismo de identificación.
4. PostgreSQL schema (`public` vs. schema dedicado).
5. Restricciones `CHECK`, `UNIQUE` y `FOREIGN KEY`.
6. Mecanismo exacto de idempotencia.
7. Implementación de correcciones desde Telegram/n8n.
8. Estrategia de cierre mensual.
9. Consultas SQL para saldo y reportes.
10. Integración Python ↔ PostgreSQL ↔ n8n.
11. Manejo de errores y transacciones.
12. Estrategia de tests del ledger.

Estos puntos corresponden a las siguientes secciones y no deben resolverse prematuramente aquí.

---

## Estado

**2.3 — Data Model & Ledger Design: propuesta consolidada.**

Esta versión incorpora la revisión cruzada y corrige las principales ambigüedades identificadas:

- El alcance matemático queda explícitamente limitado a una relación bilateral.
- Se elimina `Person.role`.
- Se incorpora `source_reference` como punto de extensión para idempotencia.
- Las correcciones pueden reemplazar el evento completo.
- Las correcciones pueden encadenarse.
- No existe bloqueo técnico por antigüedad en v1.
- La documentación pública utiliza identificadores genéricos y datos sintéticos.

**Siguiente etapa:** `2.4 — Application & Integration Architecture`.
