# PHASE 2.12 — PLAN DE TRABAJO CODEX ↔ CLAUDE CODE

**Proyecto:** Personal Expense Ledger — Telegram + n8n + Python + PostgreSQL
**Fase:** 2 — Technical Design
**Sección:** 2.12 — Plan de ejecución con agentes (último documento de Fase 2)
**Estado:** CERRADO
**Fecha:** 2026-08-31
**Nota:** Este documento fue redactado únicamente por Claude, tras la decisión de Erick de cerrar la Fase 2 sin participación de GPT en esta sección final. No contradice ninguna decisión previamente validada por ambos.

---

## 1. Propósito

Definir cómo se va a ejecutar la implementación real de este piloto usando Codex y Claude Code en paralelo — no solo como herramientas de código, sino como el experimento central del objetivo más amplio de Erick: descubrir su metodología ideal de trabajo con agentes antes de diseñar el framework personal definitivo.

Este documento no redefine ninguna decisión de dominio, arquitectura, seguridad o testing ya cerrada en 2.1–2.11. Traduce esas decisiones en un plan operativo de ejecución.

---

# 2. Estado de partida

* Ni Codex ni Claude Code están instalados todavía.
* La instalación y primeros pasos de cada herramienta se enseñan por separado (ChatGPT para Codex, Claude para Claude Code, como se acordó desde el inicio de este proyecto) — no es parte del contenido de este documento, pero sí el primer paso operativo antes de que el plan de abajo pueda ejecutarse.
* No existe código del proyecto todavía. Fase 2 completa (2.1–2.11) es el único insumo.

---

# 3. Estrategia de contexto/memoria entre agentes

Decisión ya tomada por Erick (acordada también con GPT): **el conocimiento del proyecto vive en el repositorio, no en la memoria de cada conversación**. Ambos agentes leen los mismos documentos versionados en vez de que Erick les explique el proyecto desde cero cada vez.

Esto retoma directamente lo que quedó deliberadamente abierto en 2.2 (`.ai/` sin estructura interna definida, "se diseñará después de observar cómo Codex y Claude Code trabajan realmente con el proyecto"). Este es exactamente ese momento — pero el punto de partida sigue siendo mínimo, no se diseña la estructura completa por adelantado:

```text
.ai/
├── project.md       ← qué es el proyecto, en 1-2 párrafos, con links a docs/decisions/
└── decisions.md      ← resumen curado de decisiones cerradas (no el historial completo de debate)

docs/decisions/
└── phase-1-and-2/    ← los documentos 2.1–2.11 tal cual, como fuente completa de verdad

AGENTS.md              ← reglas generales (matriz de autoridad, §6 de este documento)
CLAUDE.md               ← específico de Claude Code, referencia a AGENTS.md sin duplicar
```

Principio operativo: **cada agente lee `.ai/project.md` y `AGENTS.md`/`CLAUDE.md` al iniciar una tarea, y consulta `docs/decisions/` o el código existente solo cuando la tarea concreta lo requiere** — no se le vuelca todo el histórico de Fase 1/2 en cada prompt. Qué tan bien funciona esto (si los agentes realmente encuentran lo que necesitan, si falta algo, si algo sobra) es precisamente una de las cosas que este piloto debe medir (§7).

---

# 4. Orden de construcción

Erick no tiene preferencia fija, así que se propone lo siguiente con su justificación, no como imposición:

**Empezar por el núcleo de dominio financiero, no por infraestructura.**

Razones:

* El modelo de datos, las reglas de signo, el parser determinístico y las correcciones (2.3, 2.6 parcialmente) son 100% probables en local con `pytest` + PostgreSQL, sin Telegram, sin n8n, sin Docker, sin VPS.
* Es la pieza más crítica y más fácil de auditar objetivamente entre agentes — hay un resultado matemáticamente correcto contra el cual comparar, a diferencia de decisiones de infraestructura donde "correcto" es más subjetivo.
* Permite el primer ciclo completo de revisión cruzada (implementar → revisar) en días, no semanas, sin esperar a tener Docker/CI/CD funcionando.
* Si algo del modelo de datos necesita ajustarse al enfrentarlo con código real, es mejor descubrirlo ahora que después de construir toda la infraestructura alrededor.

Orden propuesto de bloques (ajustable tras el primer ciclo, ver §7):

```text
1. Modelo de datos + migraciones Alembic (2.3, 2.6)
2. Reglas financieras puras: signed_effect, cálculo de saldo, correcciones (2.3)
3. Parser determinístico + contrato de fallback LLM, sin conectar LLM real todavía (2.3 §16-19, 2.5)
4. API FastAPI sobre lo anterior (2.5)
5. Contenedor Docker + Compose local (2.7)
6. Integración n8n + Telegram (2.10) — la primera vez que se toca infraestructura real del VPS
7. Reportes (2.8/2.9 numeración GPT, correspondiente a "2.09 Reportes" en el índice original)
8. CI/CD + deployment real a VPS (2.7, 2.11)
```

Los bloques 1-4 pueden desarrollarse y validarse íntegramente en local. El bloque 6 es el primer punto de contacto con el VPS real.

---

# 5. Primer experimento de asignación de roles

Continuando lo ya decidido en Fase 1 y GPT (Fase 2 sección "2.5" histórica): el primer ciclo será

```text
Claude Code implementa el bloque 1 (modelo de datos + migraciones)
        ↓
Codex revisa, buscando específicamente errores de signo/integridad
```

Esto no es una asignación permanente — es el punto de partida deliberado para tener un primer dato comparable. A partir del segundo bloque, Erick decide si mantiene el mismo patrón, lo invierte, o prueba el "Experimento C" que GPT propuso en Fase 1 (ambos agentes resuelven el mismo bloque de forma independiente y Erick compara). Esa decisión se toma con la evidencia del primer ciclo (§7), no de antemano.

---

# 6. Matriz de autoridad (consolidación final, sin cambios de fondo respecto a Fase 1/2.6/2.7)

### Los agentes pueden, sin pedir aprobación:

* leer el repositorio y la documentación;
* crear y modificar código de la aplicación;
* crear y ejecutar tests;
* ejecutar linters/análisis estático;
* crear commits locales;
* proponer cambios y documentar decisiones;
* revisar el trabajo del otro agente.

### Requieren aprobación explícita de Erick:

* operaciones destructivas (`DROP`, eliminación de datos);
* cambios de arquitectura respecto a lo ya cerrado en 2.1–2.11;
* cualquier cosa que toque producción (VPS real, PostgreSQL de producción);
* manejo de secretos/credenciales;
* migraciones potencialmente destructivas (2.8 §26);
* `git push` y `merge` — siempre acción humana, ningún agente empuja código directamente.

Esta matriz aplica igual para Codex y Claude Code, sin excepción para ninguno.

---

# 7. Qué se registra durante el piloto (bitácora mínima)

El objetivo explícito de Erick no es solo tener el bot funcionando, sino aprender su propia metodología ideal. Por eso, cada ciclo de trabajo (bloque de la lista de §4) se registra con una entrada breve — no un reporte elaborado, solo lo necesario para comparar ciclos entre sí después:

```text
Bloque:                 [ej. "Modelo de datos"]
Agente implementador:   [Codex / Claude Code]
Agente revisor:         [Codex / Claude Code]
Tiempo aproximado:      [implementación / revisión]
Intervenciones de Erick: [cuántas veces tuvo que corregir dirección, cuántas fueron dudas normales]
Hallazgos del revisor:  [cuántos, de qué tipo: error real / estilo / falso positivo]
Archivos de .ai/docs/   [cuáles leyó cada agente realmente — si se puede observar; cuáles nunca se usaron]
  realmente consultados
Nota libre:             [cualquier fricción o sorpresa que valga la pena recordar]
```

Esta bitácora es la que después informa las decisiones que Erick pospuso deliberadamente durante todo este proceso: granularidad ideal de revisión cruzada, qué tan grande debe ser cada entrega antes de revisión, qué contenido de `.ai/`/`docs/` realmente se usa (y por tanto qué vale la pena mantener) y cuál sobra, y finalmente cómo debe verse el framework personal definitivo.

---

# 8. Punto de control tras el primer ciclo

Al terminar el bloque 1 (modelo de datos) con su revisión cruzada, antes de continuar con el bloque 2, Erick revisa la bitácora y decide explícitamente:

* si mantiene Claude-implementa/Codex-revisa o invierte los roles;
* si la granularidad de revisión (un bloque completo) fue adecuada o conviene más pequeña/grande;
* si algo de `.ai/`/`docs/decisions/` no se usó y se puede simplificar;
* si algo faltó y los agentes tuvieron que preguntarle a Erick información que debería haber estado documentada.

Este punto de control se repite, informalmente, después de cada bloque — no hace falta un documento nuevo cada vez, basta con la bitácora del §7 y una decisión rápida antes de seguir.

---

# 9. Qué NO se resuelve en este documento

* La estructura definitiva de `.ai/` — sigue siendo deliberadamente mínima y sujeta a lo que el uso real demuestre.
* Cuál de los dos agentes termina siendo mejor para qué tipo de tarea — es precisamente lo que el piloto debe descubrir, no algo que se decide de antemano.
* El diseño del framework personal portable definitivo — ese es el objetivo final de todo este proceso, y se aborda después de completar este piloto con evidencia real, no antes.

---

## Criterio de cierre de 2.12 y de Fase 2 completa

Fase 2 se considera cerrada cuando:

* [x] 2.1 — Arquitectura física
* [x] 2.2 — Estructura del repositorio
* [x] 2.3 — Modelo de datos y ledger
* [x] 2.4/2.5 — Arquitectura de aplicación y contrato de API
* [x] 2.6 — Persistencia, migraciones e idempotencia
* [x] 2.7 — Deployment, runtime y CI/CD
* [x] 2.8/2.9 — Testing y validación
* [x] 2.9/2.10 (numeración final) — Reportes y notificaciones
* [x] 2.10 — Telegram ↔ n8n: estados, botones y UX (registro + corrección)
* [x] 2.11 — Security + Secrets
* [x] 2.12 — Plan de trabajo Codex ↔ Claude Code

**FASE 2 — CERRADA.**

**Comienza Fase 3 — Implementación**, empezando por instalar y aprender a usar Claude Code y Codex, y luego el bloque 1 del orden definido en §4.
