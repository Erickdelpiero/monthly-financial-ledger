# 2.4 — Application & Integration Architecture

**Proyecto:** Personal Expense & Debt Ledger  
**Fase:** 2 — Technical Design  
**Sección:** 2.4 — Application & Integration Architecture  
**Estado:** Final  
**Fecha:** 2026-08-30

---

## 1. Objetivo

Definir cómo interactúan los componentes de la aplicación en desarrollo y producción, manteniendo una separación clara entre interfaz de usuario, orquestación, estado conversacional, lógica de negocio, persistencia, integración con Telegram, generación de reportes y fallback mediante LLM.

La arquitectura debe ser suficientemente simple para este experimento, pero reproducible y portable como referencia para el framework futuro.

---

## 2. Arquitectura propuesta

### Componentes

1. **Telegram Bot**
   - Interfaz de entrada para los usuarios.
   - Envía mensajes y botones.
   - No contiene lógica financiera.

2. **n8n**
   - Orquestador de workflows.
   - Recibe eventos de Telegram mediante webhook.
   - Gestiona el flujo conversacional multi-turno.
   - Presenta botones y solicita información.
   - Invoca al backend Python.
   - Ejecuta tareas programadas de reportes.
   - Gestiona la credencial del bot de Telegram.
   - No contiene la lógica financiera central.

3. **Python Backend**
   - Núcleo de aplicación.
   - Parser determinístico.
   - Fallback LLM.
   - Validaciones.
   - Cálculo del efecto firmado de cada evento.
   - Cálculo del saldo.
   - Correcciones.
   - Generación de reportes e imágenes.

4. **PostgreSQL**
   - Persistencia del ledger.
   - En producción reutilizará la instancia PostgreSQL existente, pero mediante una base de datos y un rol propios del proyecto.
   - En desarrollo también se utilizará PostgreSQL.

5. **LLM Provider**
   - Dependencia secundaria.
   - Se utiliza únicamente como fallback del parser determinístico.
   - No determina `event_type`, `payer`, `signed_effect` ni `balance`.

6. **GitHub**
   - Repositorio público.
   - Fuente de verdad del código y documentación no sensible.

7. **CI/CD**
   - Automatización de validación y despliegue.
   - La implementación concreta se definirá posteriormente.

---

## 3. Principio fundamental de separación de responsabilidades

> **Telegram presenta; n8n orquesta; Python decide; PostgreSQL persiste; el LLM interpreta únicamente cuando sea necesario.**

### n8n NO debe:

- calcular saldos;
- implementar reglas contables;
- determinar signos financieros;
- modificar directamente tablas del ledger;
- duplicar la lógica de Python mediante Code Nodes.

### Python debe ser la fuente única de verdad para:

- `event_type → signed_effect`;
- validación de transacciones;
- cálculo del saldo;
- aplicación de correcciones;
- parsing determinístico;
- fallback LLM;
- generación de reportes;
- generación de imágenes.

---

## 4. Flujo principal de registro

El registro de una operación es multi-turno:

```text
Usuario
   │
   ▼
Telegram
   │
   ▼
n8n
   │
   ├── Identifica Telegram user_id
   ├── Inicia/recupera sesión conversacional
   ├── Presenta tipo de operación
   ├── Recibe monto/descripcion
   ├── Solicita fecha
   └── Solicita confirmación
   │
   ▼
Python Backend
   │
   ├── Parser determinístico
   ├── LLM fallback si corresponde
   ├── Validación
   ├── Determina signed_effect
   └── Persiste transacción
   │
   ▼
PostgreSQL
   │
   ▼
Python Backend
   │
   └── Calcula saldo actualizado
   │
   ▼
n8n
   │
   ▼
Telegram
```

---

## 5. Estado conversacional multi-turno

El flujo requiere recordar, entre mensajes independientes de Telegram, en qué paso se encuentra cada usuario.

### Dueño del estado

El **estado conversacional temporal será responsabilidad de n8n**, no del dominio financiero de Python.

El estado mínimo puede incluir:

```text
telegram_user_id
current_step
selected_event_type
pending_amount
pending_description
pending_event_date
expiration / cleanup metadata
```

Este estado representa una **sesión de entrada pendiente**, no una transacción financiera.

La transacción solo se persistirá en PostgreSQL cuando el flujo haya sido validado y confirmado.

### Principio de separación

```text
n8n
  └── estado temporal de interacción

Python
  └── verdad del dominio financiero

PostgreSQL
  └── persistencia del ledger
```

La tecnología exacta para persistir temporalmente este estado se definirá en el diseño de workflows.

---

## 6. Telegram

Telegram será la interfaz principal del MVP.

El diseño inicial utilizará principalmente:

- botones;
- opciones predefinidas;
- respuestas cortas;
- selección explícita de fecha;
- ingreso de monto;
- descripción libre cuando sea necesaria.

Se evita inicialmente un chatbot basado en NLG.

La decisión de utilizar LLM para interpretar mensajes más libres podrá reevaluarse después del primer mes de uso real.

El usuario será identificado mediante `telegram_user_id`. El backend no deberá confiar en un nombre escrito por el usuario para determinar quién realiza la operación.

---

## 7. Telegram mediante webhook

La arquitectura utilizará **Telegram mediante webhook HTTPS**.

La infraestructura existente dispone de:

```text
https://n8n.gonex.pe/
```

y actualmente existe el flujo:

```text
Internet
   │
   ▼
Cloudflare
   │
   ▼
Nginx :443
   │
   ▼
n8n :5678
```

La configuración observada en el VPS incluye:

```text
server_name n8n.gonex.pe;
proxy_pass http://localhost:5678;
```

y n8n tiene:

```text
N8N_HOST=n8n.gonex.pe
N8N_PROTOCOL=https
WEBHOOK_URL=https://n8n.gonex.pe/
```

La integración definitiva con el bot específico del proyecto se validará durante la implementación.

---

## 8. n8n

Se mantendrá inicialmente la instancia de n8n existente como servicio de infraestructura compartida.

No se levantará una segunda instancia completa de n8n para este experimento salvo que una necesidad concreta lo justifique.

El workflow del proyecto deberá permanecer aislado lógicamente de los workflows existentes.

Flujo conceptual:

```text
Telegram Trigger
      │
      ▼
Conversation State
      │
      ▼
Input Collection
      │
      ▼
HTTP Request → Python API
      │
      ▼
Receive Result
      │
      ▼
Telegram Response
```

n8n puede manejar control de flujo y estado de interacción, pero no debe replicar las reglas financieras.

---

## 9. Python Backend

Python será el núcleo de aplicación.

Responsabilidades:

- recibir solicitudes de n8n;
- validar estructura;
- ejecutar el parser determinístico;
- invocar el LLM únicamente como fallback;
- validar el resultado;
- calcular `signed_effect`;
- persistir transacciones;
- calcular saldo;
- aplicar correcciones;
- generar reportes e imágenes.

El LLM inicialmente solo podrá devolver:

- `amount`;
- `description`.

Nunca deberá decidir:

- `event_type`;
- `payer`;
- `signed_amount`;
- `balance`.

---

## 10. API interna

La comunicación n8n → Python se realizará mediante una API HTTP interna.

```text
n8n
 │
 │ HTTP
 ▼
Python API
 │
 ├── application logic
 └── database access
```

La API validará nuevamente las solicitudes provenientes de n8n.

El mecanismo exacto de autenticación entre n8n y Python se definirá en el diseño de API y seguridad.

---

## 11. Exposición del Python Backend

El backend Python no necesita estar públicamente expuesto a Internet en la primera versión.

Preferencia:

```text
Telegram
   │
   ▼
n8n
   │
   ▼
Python
   │
   ▼
PostgreSQL
```

Cuando sea posible, Python se ejecutará dentro de la infraestructura de producción y se comunicará internamente.

No se expondrá públicamente PostgreSQL ni, salvo necesidad justificada, el puerto del backend.

---

## 12. PostgreSQL

### Producción

Se reutilizará la instancia PostgreSQL existente del VPS, con aislamiento lógico obligatorio:

```text
PostgreSQL instance
        │
        ├── n8n database / roles existentes
        │
        └── proyecto ledger
              ├── database propia
              └── role propio
```

El proyecto nunca utilizará:

- usuario administrativo `postgres`;
- credenciales de n8n;
- credenciales administrativas de la instancia;
- tablas internas de n8n.

El rol del proyecto tendrá únicamente los privilegios necesarios.

### Desarrollo

Se utilizará **PostgreSQL también durante desarrollo**.

La instancia de desarrollo será independiente de producción.

La forma exacta de ejecutar PostgreSQL localmente se definirá durante la implementación del entorno de desarrollo.

---

## 13. Docker y red

El proyecto tendrá su propio entorno Docker cuando sea necesario.

Su `docker-compose.yml` será independiente del compose privado de GONEX y no deberá depender directamente de:

```text
~/gonex/docker/.env
```

ni incorporar secretos de la infraestructura privada.

Actualmente existe:

```text
docker_gonex-network
```

que conecta múltiples servicios de GONEX.

El proyecto no asumirá automáticamente que debe conectarse a toda esa red. La necesidad de utilizarla se evaluará durante el diseño de despliegue.

Principio:

> reutilizar infraestructura existente cuando aporte valor, pero no heredar exposición de red innecesaria.

---

## 14. Idempotencia

El uso de webhook hace que la idempotencia sea un requisito concreto.

Un mismo evento de Telegram no debe producir dos transacciones financieras por un reintento o procesamiento duplicado.

```text
Telegram event
      │
      ▼
Idempotency check
      │
      ├── already processed → no duplicate transaction
      │
      └── new event → process
```

El mecanismo exacto de idempotencia se definirá en el diseño de persistencia/API.

---

## 15. LLM Fallback

```text
Input
  │
  ▼
Deterministic Parser
  │
  ├── éxito ───────────────► Validación
  │
  └── fallo
         │
         ▼
      LLM Fallback
         │
         ▼
      Validación
         │
         ▼
       Persistencia
```

El resultado del LLM nunca se considerará confiable por defecto y deberá pasar por validación determinística.

---

## 16. Reportes

Los reportes serán generados por Python.

```text
Scheduler n8n
      │
      ▼
Python
      │
      ├── obtiene transacciones
      ├── aplica correcciones
      ├── calcula saldo
      ├── genera reporte
      └── genera imagen
      │
      ▼
n8n
      │
      ▼
Telegram
```

La imagen del reporte también será generada mediante Python.

n8n únicamente coordinará el envío.

---

## 17. Auditoría mensual

Al realizar el reporte:

1. Se generan los resultados del período.
2. Se revisan las operaciones.
3. Se verifica el saldo.
4. Se identifican operaciones faltantes o incorrectas.
5. Se realizan correcciones si corresponde.
6. Se vuelve a generar el reporte.
7. El período se considera revisado cuando Erick confirma que todo está correcto.

En v1 no existirá un sistema contable formal de períodos cerrados.

Las correcciones históricas seguirán técnicamente permitidas.

---

## 18. Correcciones

Una corrección reemplaza conceptualmente un evento anterior y puede modificar los campos permitidos del evento, incluyendo:

- tipo de evento;
- monto;
- descripción;
- fecha del evento.

El evento original permanece para auditoría y se marca como no activo.

El saldo se calcula únicamente utilizando:

```text
status = ACTIVE
```

Las correcciones pueden encadenarse:

```text
A → B → C
```

El cálculo del saldo solo utiliza el evento actualmente `ACTIVE`.

No existe una restricción técnica de ventana temporal para las correcciones en v1.

---

## 19. Seguridad y privacidad

### Secretos

Nunca deberán almacenarse en Git:

- tokens de Telegram;
- credenciales PostgreSQL;
- API keys;
- credenciales n8n;
- claves del proveedor LLM;
- `.env` reales.

El repositorio público utilizará `.env.example` con valores ficticios.

### Datos financieros

Los datos financieros reales se consideran privados.

**Ningún dato financiero real generado durante la ejecución se almacenará en el repositorio público.**

Esto incluye:

- montos reales;
- saldos;
- descripciones reales;
- reportes reales;
- imágenes reales;
- logs con datos financieros;
- payloads reales;
- exports de base de datos.

El repositorio podrá contener únicamente datos sintéticos, fixtures artificiales, tests, ejemplos anonimizados y documentación conceptual.

---

## 20. Desarrollo local → producción

```text
Local Development
       │
       ▼
Tests
       │
       ▼
Git
       │
       ▼
GitHub
       │
       ▼
CI/CD
       │
       ▼
VPS
       │
       ▼
Production
```

El desarrollo de Python, lógica de negocio, PostgreSQL y tests se realizará principalmente en local.

La integración real con n8n, Telegram y webhook se validará posteriormente en producción.

---

## 21. CI/CD

El repositorio será público y deberá poder desplegarse de forma reproducible.

Objetivo:

```text
commit
   ↓
test
   ↓
build/deploy
   ↓
VPS
```

La solución concreta se definirá posteriormente, evitando infraestructura innecesaria.

---

## 22. Agentes: Codex + Claude Code

Codex y Claude Code pueden:

- implementar código;
- crear tests;
- revisar código;
- proponer cambios;
- documentar decisiones;
- ejecutar verificaciones.

No deben decidir autónomamente:

- reglas financieras;
- modelo conceptual del ledger;
- permisos críticos;
- exposición de secretos;
- cambios arquitectónicos relevantes.

Las decisiones arquitectónicas importantes deben quedar documentadas y aprobadas por Erick.

---

## 23. División de responsabilidades

| Componente | Responsabilidad principal |
|---|---|
| Telegram | Interfaz |
| n8n | Orquestación + estado conversacional temporal |
| Python | Lógica de aplicación |
| PostgreSQL | Persistencia |
| LLM | Fallback de parsing |
| GitHub | Control de versiones |
| CI/CD | Automatización de despliegue |
| Docker | Empaquetado/ejecución |
| Erick | Decisiones de producto y arquitectura |

---

## 24. Principios de diseño

### P1 — Single Source of Truth
Python es la fuente única de verdad de la lógica financiera.

### P2 — Deterministic First
Las reglas determinísticas tienen prioridad sobre el LLM.

### P3 — Thin Orchestration
n8n coordina y mantiene estado conversacional temporal, pero no implementa el dominio financiero.

### P4 — Least Privilege
Cada componente tendrá únicamente los permisos necesarios.

### P5 — Private by Default
Los datos financieros reales nunca deberán entrar al repositorio público.

### P6 — Reproducibility
El proyecto debe poder reconstruirse desde el repositorio.

### P7 — Minimal Infrastructure
No se crearán servicios separados sin una necesidad demostrada.

### P8 — Production Reality
Las decisiones deben considerar el entorno real de producción, pero la lógica de negocio debe poder probarse localmente.

### P9 — Explicit Decisions
Los agentes no deben resolver por inferencia las decisiones arquitectónicas relevantes.

### P10 — Reversible Decisions
Cuando una decisión no necesite ser definitiva, se preferirá una solución simple y reversible.

---

## 25. Decisiones heredadas y pendientes

### Ya decidido

- Telegram mediante webhook HTTPS.
- n8n existente como orquestador inicial.
- n8n como dueño del estado conversacional temporal.
- Python como núcleo de negocio.
- PostgreSQL desde desarrollo.
- PostgreSQL dedicado lógicamente en producción.
- LLM únicamente como fallback.
- generación de imágenes mediante Python.
- datos financieros reales fuera del repositorio público.
- idempotencia como requisito.

### Pendiente de diseño técnico posterior

1. esquema SQL definitivo;
2. estructura exacta de la API;
3. framework concreto de Python;
4. mecanismo concreto de estado conversacional en n8n;
5. mecanismo de autenticación n8n → Python;
6. estrategia exacta de Docker;
7. topología definitiva de red;
8. proveedor LLM;
9. estrategia concreta de CI/CD;
10. estrategia de backup/restore;
11. observabilidad y logging.

---

## 26. Nota sobre extensibilidad

El ledger de v1 es deliberadamente **bilateral**.

La entidad `Person` permanece normalizada, pero el saldo `S` está definido para la relación entre los dos participantes actuales.

Agregar una tercera persona en el futuro requeriría rediseñar el cálculo de saldo; no se considera una extensión incremental del modelo matemático actual.

Asimismo, cualquier campo de `Person` sin una necesidad funcional demostrada se evitará en v1.

---

## 27. Arquitectura objetivo

```text
                         INTERNET
                            │
                            ▼
                       Cloudflare
                            │
                            ▼
                       Nginx :443
                            │
                            ▼
                    n8n.gonex.pe
                            │
                            ▼
                    ┌──────────────┐
                    │     n8n      │
                    │ Orchestrator │
                    │ + Conv State │
                    └──────┬───────┘
                           │
                           │ HTTP/internal
                           ▼
                    ┌──────────────┐
                    │    Python    │
                    │ Application  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
          PostgreSQL     Parser       LLM
              │        Deterministic  Fallback
              │
              ▼
       Financial Ledger
              │
              ▼
        Report Generator
              │
              ▼
             n8n
              │
              ▼
           Telegram


Local Development
      │
      ▼
     Git
      │
      ▼
   GitHub
      │
      ▼
    CI/CD
      │
      ▼
     VPS
```

---

## 28. Criterio de cierre de 2.4

- [x] Componentes principales definidos.
- [x] Responsabilidades de cada componente definidas.
- [x] n8n no contiene la lógica financiera central.
- [x] Python es la fuente única de verdad del dominio.
- [x] Flujo Telegram → n8n → Python → PostgreSQL definido.
- [x] Estado conversacional multi-turno definido.
- [x] LLM definido como fallback.
- [x] Flujo de reportes definido.
- [x] Estrategia general local → GitHub → producción definida.
- [x] Aislamiento de datos y secretos documentado.
- [x] Idempotencia establecida como requisito.
- [x] No quedan decisiones críticas que deban ser resueltas por inferencia de los agentes.

---

**Estado:** Final — lista para continuar con 2.5.
