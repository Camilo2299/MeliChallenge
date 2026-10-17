# Challenge — DevOps & Platform Engineering

**Ampliación de telemetría real:** [flujo CloudWatch/ECS → DynamoDB → API/dashboard](docs/telemetry.md). Desplegada y validada funcionalmente; [capacidad real](docs/telemetry-capacity-results.md): 5k RPS/60 s y 10k RPS/30 s (el intento de 60 s falló por descartes). Las evidencias de 10.000 RPS siguientes corresponden a la versión anterior con fixtures.

**Implementación de referencia:** API REST de estado de infraestructura con Go (`net/http`), dockerización, pruebas unitarias, IaC para AWS ECS Fargate, CI/CD GitHub Actions y decisiones de producción explícitas.

> **Datos y evidencia:** AWS usa CloudWatch/ECS → DynamoDB → caché de 3 s; el modo local conserva fixtures. Se validaron 5.000 RPS/60 s y 10.000 RPS/30 s contra las métricas reales. El intento real de 60 s falló por descartes: [resultados y límites](docs/telemetry-capacity-results.md). El benchmark anterior de fixtures se conserva por separado y no certifica esta versión.

## 1. Ejecutar localmente

Requiere Docker con Docker Compose:

```bash
docker compose up --build
curl -i http://localhost:8080/health/ready
curl -s http://localhost:8080/v1/services
curl -s http://localhost:8080/v1/services/gateway
curl -s 'http://localhost:8080/v1/deployments?service_id=gateway'
curl -s http://localhost:8080/v1/summary
```

Documentación: http://localhost:8080/docs; contrato OpenAPI: http://localhost:8080/openapi.json

Alternativa con Docker:

```bash
docker build -t infra-signal-api:local api
docker run --rm -p 8080:8080 --read-only --tmpfs /tmp infra-signal-api:local
```

Pruebas Go (requiere Go 1.27+):

```bash
cd api
go test -race -cover ./...
go vet ./...
go run .
```

### Por qué Go

Go permite compilar un binario estático y atender solicitudes concurrentes con `net/http`, sin dependencias externas. La imagen final usa `scratch`, usuario sin privilegios y un health check integrado en el binario. Se configuran timeouts HTTP y apagado gradual ante SIGTERM para ECS. Frente a Python, esperamos menor sobrecarga de CPU y memoria, pero la mejora se debe medir con la misma carga y recursos; cambiar de lenguaje no demuestra 10.000 RPS.

`/docs` contiene documentación estática; `/openapi.json` permite importar el contrato en herramientas de API.

## 2. Contrato API

| Método | Ruta | Función |
|---|---|---|
| GET | `/health/live` | Proceso vivo (liveness) |
| GET | `/health/ready` | Preparado para recibir tráfico (readiness) |
| GET | `/v1/services?environment=lab` | Inventario con filtro validado |
| GET | `/v1/services/{service_id}` | Consulta por ID, 404 uniforme |
| GET | `/v1/deployments?service_id=infra-signal-lab` | Despliegues actuales de ECS |
| GET | `/v1/summary` | Estado y frescura de la recolección |
| GET | `/v1/metrics` | Métricas reales con timestamps y series de 15 minutos |
| GET | `/v1/metrics/history` | Snapshots persistidos; últimos 30 |
| GET | `/dashboard` | Vista autenticada con Cognito; refresco cada 3 s |

Errores de negocio/validación: `{"error":{"code":"NOT_FOUND","message":"..."}}` o `{"error":{"code":"VALIDATION_ERROR","message":"...","details":[...]}}`. Identificador en respuesta `X-Request-ID`. En local se puede consultar sin token. En AWS las rutas de negocio requieren JWT de Cognito y scope `infra-metrics/read`; los errores del authorizer tienen formato de API Gateway.

## 3. Arquitectura AWS

Ver [`docs/architecture.md`](docs/architecture.md) para el diagrama y las limitaciones.

- API Gateway HTTP API con JWT de Cognito y scope `infra-metrics/read` → VPC Link → ALB interno → ECS Fargate privado en dos AZ.
- HTTPS público en el dominio AWS de API Gateway; `/health/ready` es pública. Las rutas de negocio requieren autenticación. No se publica Swagger en Gateway.
- Dos NAT Gateway, health checks, circuit breaker y autoscaling. Configuración inicial de laboratorio: 2–4 tareas, throttling 100 RPS y burst 200; el pico se validó con un perfil temporal de 16 tareas y throttle 10k que se retiró tras la prueba.
- ECR inmutable, estado S3 cifrado/versionado con lockfile, CloudWatch y roles ECS separados. Los roles GitHub OIDC están definidos en `iac/identity`; ya fueron creados mediante Terraform y su estado está en S3.
- DynamoDB almacena snapshots; Secrets Manager custodia la clave HMAC inyectada por ECS. HTTP API no tiene WAF directo en este diseño.

## 4. Despliegue y estado actual

Bootstrap, identidad OIDC y plataforma fueron aplicados con Terraform. El [pipeline de despliegue exitoso](https://github.com/Camilo2299/MeliChallenge/actions/runs/38857181854) incluye la verificación posterior. La ampliación real se aplicó con Terraform usando SSO y conserva los roles OIDC del pipeline. El [reporte de telemetría real](docs/evidence/real-telemetry.json) registra siete consultas autenticadas 200, persistencia y dos recolecciones sucesivas. El reporte anterior de cinco consultas con fixtures se conserva como histórico. Ver también [`docs/bootstrap-evidence.md`](docs/bootstrap-evidence.md). Revisar [`cicd/bootstrap.md`](cicd/bootstrap.md) para el procedimiento reproducible y [`docs/costs.md`](docs/costs.md) para costos.

GitHub Actions ejecuta pruebas Go, build Linux/amd64, escaneos y validación/pruebas Terraform en push/PR. El workflow **Lab lifecycle** agrega despliegue, rollback, plan y destrucción/reconstrucción del laboratorio. Conserva la base de control (estado, imágenes e identidad). Ver [procedimiento, alcance y límites](docs/lifecycle.md); incluye la excepción de inicialización y mantenimiento de bootstrap/identidad. Los gates del environment `production` siguen vigentes. La capacidad de destruir está preparada; no implica que se haya ejecutado un ciclo destructivo real.

No subir `.tfvars`, estados, planes, tokens ni credenciales. Los archivos `.terraform.lock.hcl` sí se versionan para Mac ARM64 y Linux AMD64. El estado bootstrap y el estado de infraestructura usan keys diferentes. El perfil humano es SSO; Actions usa OIDC, sin access keys permanentes.

Planificar el retiro del laboratorio con [`docs/runbook.md`](docs/runbook.md). AWS Budgets alerta y no corta el gasto automáticamente.

## 5. Escala 10k RPS: método de prueba y gates

1. Prueba `smoke`: 10 RPS, 60s; confirmar 0 5xx.
2. Escalado gradual: 100, 500, 1k, 5k, 10k RPS; 5 min cada tramo; generar desde load generators con capacidad suficiente, tras revisar cuotas regionales de API Gateway y ajustar el throttling del laboratorio.
3. Soak test: 10k RPS durante 30 minutos si se cumplieron los SLOs. Inyectar caída controlada de una AZ / kill de task y medir recuperación.
4. Métricas: RPS real entregado, p95/p99, errores 5xx, saturación CPU/mem, task desired/running, ALB target response time, lag del autoscaler, throttling, NAT cost.
5. Gates propuestos: éxito >=99.9%, p95 <200ms, sin errores no controlados y HA en failover. Se cumplieron los criterios de error y latencia en el pico regional de 60 s; soak y failover bajo esa carga siguen pendientes.

Guion k6 de ejemplo: [`docs/loadtest.js`](docs/loadtest.js). El guion `performance/loadtest.js` usa límites conservadores: hasta 1.000 RPS locales y 30 RPS/60 s en cloud con JWT en memoria. `docs/loadtest.js` conserva una entrada compatible. La prueba local de 100 RPS durante 60 s pasó; ver `docs/evidence/local-load.json`. El plan de cierre AWS está en `docs/validation-plan.md`. Una prueba de 10k RPS requiere otro plan, cuotas, dimensionamiento, autorización de gasto y generadores suficientes; estos resultados no se extrapolan a esa meta.

## 6. Costos / seguridad / producción

- La factura se compone de Fargate vCPU/GB-hora × tareas, ALB horas/LCUs, 2 NAT GW horas/GB, CloudWatch logs/metrics, ECR storage/scan, transferencia. Presupuestar escenarios idle, nominal y pico con la calculadora oficial, no asignar una cifra sin región, throughput y tamaño real de payload.
- Cognito, JWT con scope, logs y alarmas 5xx están implementados. El laboratorio no tiene tracing ni destino de notificación para alarmas. No se usa API key como mecanismo de autenticación. Ver `docs/architecture.md`.
- La automatización es demostrativa; añadir análisis de políticas, gates de SLO post-deploy, SBOM, signing y validaciones de drift antes de operar una plataforma enterprise.

## Documentación y evidencias

- [Cómo ejecutar y probar](run.md).
- [Checklist frente al PDF](docs/audit.md).
- [Historial del despliegue y límites comprobados](docs/deployment-progress.md).

Solo está desplegado el entorno `lab` en `us-east-1`. Los nombres de entornos GitHub `production` y `production-plan` identifican gates del pipeline; no acreditan una plataforma enterprise ni un segundo entorno AWS.

Pruebas de cierre: [resultados medidos y alcance](docs/validation-results.md), [preparación de producción](docs/production-readiness.md) y [resumen técnico](docs/delivery-summary.md).

Prueba posterior de capacidad: [escalones AWS y diagnóstico](docs/capacity-results.md). El generador regional completó 10.000 RPS por un minuto, sin errores ni descartes. Los intentos anteriores en el Mac se conservan como historial. Ver [correspondencia con el diagrama original](docs/architecture-compliance.md) para elementos opcionales no desplegados.
