# 2.08 — Reportes, Notificaciones y Resumen Financiero

**Proyecto:** Monthly Financial Ledger  
**Fase:** 2 — Technical Design  
**Sección:** 2.08 — Reports  
**Estado:** FINAL — ajustado tras validación cruzada GPT ↔ Claude  
**Alcance:** diseño funcional y técnico de los reportes y notificaciones de v1. La implementación queda para la fase posterior.

---

## 1. Propósito

Definir cómo el sistema comunicará el estado financiero del ledger a Erick y a su mamá de forma:

- simple;
- inequívoca;
- visualmente clara;
- consistente con el ledger como única fuente de verdad;
- y suficientemente útil para revisar rápidamente si todo está correcto.

La prioridad de UX es:

> **Menos información innecesaria, cero ambigüedad y lectura inmediata.**

El reporte no debe exigir conocimientos técnicos.

---

## 2. Usuarios y alcance

El sistema es un asistente personal para **dos usuarios**:

- Erick.
- Mamá.

Los reportes se generan para ambos.

No se diseña en v1 un sistema de reportes para múltiples personas ni un dashboard público.

La expansión futura a más personas requerirá revisar la semántica bilateral del saldo definida en 2.3.

---

## 3. Fuente única de verdad

Todos los reportes y notificaciones deben derivarse del ledger persistido en PostgreSQL.

```text
PostgreSQL ledger
       ↓
Python
       ↓
reporte / imagen / notificación
       ↓
n8n
       ↓
Telegram
```

Reglas:

- Python calcula el saldo.
- Python determina quién debe a quién.
- Python aplica las correcciones.
- Python genera el contenido autoritativo del reporte.
- n8n distribuye el resultado.
- Telegram solamente presenta el resultado al usuario.

Nunca deben existir dos cálculos financieros independientes, uno para cada usuario o uno en n8n y otro en Python.

---

# 4. Reporte semanal

El reporte semanal será deliberadamente simple y **solo texto**.

Su objetivo es permitir que ambos usuarios sepan rápidamente cuál es la situación actual.

Debe mostrar explícitamente:

```text
Saldo actual: S/ XX.XX
```

y quién debe a quién.

### Ejemplos conceptuales

Si Erick debe:

```text
📊 Saldo actual

Erick debe a Mamá: S/ 125.50
```

Si mamá debe:

```text
📊 Saldo actual

Mamá debe a Erick: S/ 25.50
```

Si están cuadrados:

```text
📊 Saldo actual

No hay deuda pendiente.
Saldo: S/ 0.00
```

El texto exacto de los templates podrá definirse durante implementación, pero la semántica debe mantenerse.

No se incluirá una tabla semanal salvo que una necesidad real aparezca posteriormente.

---

# 5. Reporte mensual

El reporte mensual será una **imagen PNG** generada por Python y enviada por n8n mediante Telegram.

Su función es permitir una revisión completa del período sin sacrificar simplicidad.

## 5.1 Encabezado ejecutivo

La imagen debe comenzar con un resumen muy visible:

```text
RESUMEN DEL MES
Agosto 2026

Saldo actual:
Erick debe a Mamá: S/ 125.50
```

Si el saldo es cero:

```text
Saldo actual:
No hay deuda pendiente — S/ 0.00
```

El campo `direction` se interpreta según el contrato cerrado en 2.5.

Valores conceptuales:

```text
erick_owes_mama
mama_owes_erick
null cuando S = 0
```

No se debe mostrar únicamente un número cuyo signo obligue al usuario a interpretarlo.

---

## 5.2 Tabla detallada obligatoria

El resumen **no reemplaza** el detalle transaccional.

La tabla mensual debe mostrar, como mínimo:

| Fecha | Hora | Persona | Movimiento | Monto | Descripción |
|---|---|---|---|---:|---|
| 05/08/2026 | 10:32 | Erick | Mamá me dio dinero | S/ 100.00 | Compras |
| 05/08/2026 | 13:14 | Erick | Gasté para mamá | S/ 70.00 | Supermercado |
| 08/08/2026 | 09:21 | Mamá | Le di dinero a Erick | S/ 30.00 | Efectivo |

La tabla debe permitir responder fácilmente:

- qué ocurrió;
- cuándo ocurrió;
- quién lo registró;
- qué tipo de movimiento fue;
- cuánto fue;
- y qué descripción se registró.

Las correcciones deben reflejarse respetando el modelo append-only / soft-correction establecido en 2.3 y 2.6.

---

## 5.3 Qué NO debe mostrar el reporte mensual

No se añadirá información que no aporte claridad al usuario.

En particular, v1 no necesita:

- gráficos;
- categorías de gasto;
- porcentajes;
- dashboards;
- métricas financieras avanzadas;
- visualizaciones innecesarias;
- información técnica de la base de datos;
- claves de eventos;
- `idempotency_key`;
- identificadores internos.

La regla es:

> Si una pieza de información no ayuda a Erick o a su mamá a entender o verificar el estado de la cuenta, no debe entrar al reporte.

---

# 6. Diseño visual del PNG

El diseño será simple y orientado a lectura desde Telegram.

Prioridades:

1. saldo actual muy visible;
2. quién debe a quién explícito;
3. tabla legible;
4. fechas y horas fáciles de distinguir;
5. descripción suficientemente amplia para leerla;
6. tipografía clara;
7. evitar saturación visual.

La imagen puede crecer verticalmente según la cantidad de movimientos del mes.

La tecnología concreta de renderizado queda para implementación.

Python será responsable de producir el PNG.

n8n solamente lo enviará por Telegram.

---

# 7. Notificación al registrar una transacción

Cada vez que una transacción sea registrada correctamente, el otro usuario deberá recibir una notificación.

Objetivo principal:

> Evitar que la otra persona vuelva a reportar el mismo movimiento porque desconoce que ya fue registrado.

Ejemplo:

Erick registra:

```text
Mamá me dio S/ 100.00 — Compras
```

Mamá recibe:

```text
✅ Movimiento registrado

Mamá te dio S/ 100.00
Detalle: Compras

No necesitas registrarlo nuevamente.
```

El contenido exacto será un template fijo.

La notificación debe dejar claro que:

- el movimiento ya fue registrado;
- quién lo registró;
- qué movimiento se registró;
- el monto;
- la descripción cuando corresponda;
- y que no debe volver a reportarse.

---

# 8. Notificaciones de correcciones

Una corrección también debe notificar al otro usuario.

Motivo:

Una corrección silenciosa podría dejar al otro usuario con una versión mental incorrecta del ledger y provocar registros duplicados o confusión.

Por tanto:

```text
Nueva transacción confirmada
        ↓
persistencia exitosa
        ↓
notificación al otro usuario
```

y:

```text
Corrección confirmada
        ↓
persistencia exitosa
        ↓
notificación al otro usuario
```

La notificación debe indicar que se corrigió un movimiento existente, sin necesidad de exponer detalles técnicos.

---

# 9. Regla crítica: notificar después de persistir

Nunca se enviará una notificación de "registrado" antes de que PostgreSQL confirme la persistencia exitosa.

Orden obligatorio:

```text
Usuario confirma
      ↓
n8n envía solicitud
      ↓
Python valida
      ↓
Python persiste en PostgreSQL
      ↓
PostgreSQL confirma
      ↓
Python devuelve éxito
      ↓
n8n notifica al otro usuario
```

Si la persistencia falla:

- no se debe comunicar que la transacción fue registrada;
- n8n debe recibir un error estructurado;
- el ledger permanece como estaba.

Un fallo de Telegram al entregar la notificación **no debe revertir ni invalidar una transacción ya persistida**.

---

# 10. Confirmación antes del registro

El flujo conversacional mantiene una confirmación explícita antes de comitear una nueva transacción.

El resumen de confirmación será un template fijo.

Conceptualmente:

```text
Vas a registrar:

Mamá te dio: S/ 100.00
Detalle: Compras
Fecha: 30/08/2026

¿Confirmar?
[Sí, registrar] [Cancelar]
```

Solo una confirmación positiva permite enviar la operación definitiva al endpoint de creación.

La confirmación pertenece al flujo conversacional de n8n y debe quedar reflejada explícitamente también en el diseño formal de 2.05.

---

# 11. Idempotency key y confirmación

La `idempotency_key` definitiva se genera **antes de enviar la operación confirmada a FastAPI**, en el momento en que n8n prepara el request de persistencia.

Debe quedar asociada al flujo confirmado y mantenerse estable durante los reintentos de ese mismo envío.

Conceptualmente:

```text
Inicio de flujo
      ↓
recolección de datos
      ↓
confirmación
      ↓
generación/asignación de idempotency_key
      ↓
POST /transactions
      ↓
retry, si fuera necesario
      ↓
misma idempotency_key
```

Un doble clic o retry de la misma confirmación no debe generar una nueva clave.

La restricción `UNIQUE` a nivel de PostgreSQL es la garantía definitiva contra duplicados, según 2.6/2.7.

---

# 12. Generación y distribución

Los reportes se generan automáticamente mediante n8n.

## Semanal

```text
n8n Scheduler
      ↓
Python
      ↓
calcula saldo
      ↓
genera texto
      ↓
n8n
      ↓
Telegram
```

## Mensual

```text
n8n Scheduler
      ↓
Python
      ↓
consulta ledger
      ↓
aplica correcciones
      ↓
calcula saldo
      ↓
genera tabla
      ↓
renderiza PNG
      ↓
n8n
      ↓
Telegram
```

La automatización no debe duplicar lógica financiera en n8n.

---

# 13. Errores de generación de reportes

Un fallo al generar o entregar un reporte no modifica el ledger.

Por ejemplo:

```text
Ledger correcto
     +
Reporte fallido
```

debe mantenerse como:

```text
Ledger correcto
```

y el fallo debe registrarse para diagnóstico.

Los reportes son una representación derivada, no una fuente de verdad.

---

# 14. Privacidad

Los reportes contienen información financiera real.

Por tanto:

- no deben almacenarse en el repositorio público;
- no deben aparecer en commits;
- no deben incluirse como fixtures reales;
- no deben registrarse innecesariamente en logs;
- las pruebas utilizan datos sintéticos.

El PNG mensual generado en producción es un artefacto privado de runtime.

---

# 15. Reglas no negociables

1. El saldo siempre proviene de Python + ledger.
2. El reporte nunca calcula independientemente el saldo.
3. El reporte mensual conserva el detalle transaccional.
4. El reporte semanal es texto.
5. El reporte mensual es PNG.
6. Ambos usuarios reciben los reportes.
7. Ambos usuarios reciben notificaciones relevantes.
8. Una transacción se notifica solo después de persistirse correctamente.
9. Una corrección también genera notificación al otro usuario.
10. El usuario debe confirmar antes del registro definitivo.
11. Los templates de Telegram son fijos; no se usa NLG para estas respuestas.
12. Los reportes no contienen identificadores técnicos.
13. Un fallo de Telegram no altera el ledger.
14. Un fallo del generador de reportes no altera el ledger.
15. Los datos financieros reales nunca entran al repositorio público.

---

# 16. Qué queda para implementación

No se sobre-diseñan detalles que no son necesarios para cerrar esta arquitectura.

Durante implementación se decidirán:

- template exacto de los mensajes;
- tipografía y dimensiones del PNG;
- manejo visual de tablas largas;
- biblioteca concreta de renderizado;
- nombres exactos de workflows n8n;
- mecanismo concreto de reintento de entrega de Telegram;
- logging operativo del proceso de generación.

Estas decisiones no pueden modificar las reglas funcionales anteriores.

---

# 17. Dependencias documentales para cierre de Fase 2

Esta sección queda cerrada como **2.08 — Reportes**.

Para mantener la numeración oficial de la Fase 2, los documentos existentes se tratarán así:

| Sección oficial | Documento / tratamiento |
|---|---|
| 2.01 | `PHASE-2.1-PHYSICAL-ARCHITECTURE.md` — cerrado |
| 2.02 | `PHASE-2.2-REPOSITORY-STRUCTURE-FINAL.md` — cerrado |
| 2.03 | `2.3_Data_Model_and_Ledger_Design_v1.1.md` — cerrado |
| 2.04 | `2.4_Application_Integration_Architecture.md` + `2.5-API-Service-Contract-FINAL.md` — cerrado |
| 2.05 | Consolidación breve pendiente: Telegram ↔ n8n, incluyendo confirmación y ciclo de vida del estado |
| 2.06 | Cubierto por 2.3/2.5/2.7 — no rehacer |
| 2.07 | Cubierto por 2.3/2.6 — no rehacer |
| 2.08 | **Este documento — cerrado** |
| 2.09 | `2.8-testing-validation-architecture.md` — renumerar/retitular como 2.09 |
| 2.10 | Consolidación breve pendiente: Security + Secrets |
| 2.11 | `2.7-Deployment-Runtime-CICD-Architecture-FINAL.md` — cerrado |
| 2.12 | Trabajo nuevo: plan operativo Codex ↔ Claude Code |

No se deben rehacer documentos ya cerrados únicamente para hacer coincidir la numeración. Cuando exista una decisión histórica en un documento anterior, prevalece la decisión final consolidada y debe evitarse cualquier contradicción silenciosa.

---

# 18. Estado

**2.08 — FINAL**

El diseño de reportes y notificaciones queda suficientemente definido para implementación.

No se introducen dashboards, categorización, gráficos ni infraestructura adicional.

**Siguiente trabajo relevante:** consolidar 2.05 y 2.10 de forma breve, renumerar 2.09, y posteriormente diseñar 2.12 — Plan de trabajo Codex ↔ Claude Code.
