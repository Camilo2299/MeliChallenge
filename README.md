# Challenge — DevOps & Platform Engineering

**Ampliación de telemetría real:** [flujo CloudWatch/ECS → DynamoDB → API/dashboard](docs/telemetry.md). Implementación en validación; las evidencias de 10.000 RPS siguientes corresponden a la versión anterior con fixtures.

**Implementación de referencia:** API REST de estado de infraestructura con Go (`net/http`), dockerización, pruebas unitarias, IaC para AWS ECS Fargate, CI/CD GitHub Actions y decisiones de producción explícitas.

> **Transparencia:** la API funciona con datos *sample*, no consulta sistemas reales. Se validó un pico regional de **10.000 RPS durante 60 segundos** en GET /v1/services con fixtures y 16 tareas; [reporte y límites](docs/capacity-results.md). No acredita carga sostenida ni pérdida de AZ bajo ese pico. El laboratorio AWS fue desplegado mediante GitHub Actions y Terraform; se comprobaron readiness, rechazo sin token y cinco consultas autenticadas. Ver [evidencias](docs/deployment-progress.md).

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
| GET | `/v1/services?environment=production` | Inventario con filtro validado |
| GET | `/v1/services/{service_id}` | Consulta por ID, 404 uniforme |
| GET | `/v1/deployments?service_id=gateway` | Eventos de despliegue ilustrativos |
| GET | `/v1/summary` | Agregados y uptime del proceso |

Errores de negocio/validación: `{"error":{"code":"NOT_FOUND","message":"..."}}` o `{"error":{"code":"VALIDATION_ERROR","message":"...","details":[...]}}`. Identificador en respuesta `X-Request-ID`. En local se puede consultar sin token. En AWS las rutas de negocio requieren JWT de Cognito y scope `infra-metrics/read`; los errores del authorizer tienen formato de API Gateway.

## 3. Arquitectura AWS

Ver [`docs/architecture.md`](docs/architecture.md) para el diagrama y las limitaciones.

- API Gateway HTTP API con JWT de Cognito y scope `infra-metrics/read` → VPC Link → ALB interno → ECS Fargate privado en dos AZ.
- HTTPS público en el dominio AWS de API Gateway; `/health/ready` es pública. Las rutas de negocio requieren autenticación. No se publica Swagger en Gateway.
- Dos NAT Gateway, health checks, circuit breaker y autoscaling. Configuración inicial de laboratorio: 2–4 tareas, throttling 100 RPS y burst 200; el pico se validó con un perfil temporal de 16 tareas y throttle 10k que se retiró tras la prueba.
- ECR inmutable, estado S3 cifrado/versionado con lockfile, CloudWatch y roles ECS separados. Los roles GitHub OIDC están definidos en `iac/identity`; ya fueron creados mediante Terraform y su estado está en S3.
- HTTP API no tiene WAF directo en este diseño. No se crean secretos sin necesidad.

## 4. Despliegue y estado actual

Bootstrap, identidad OIDC y plataforma fueron aplicados con Terraform. El [pipeline de despliegue exitoso](https://github.com/Camilo2299/MeliChallenge/actions/runs/38857181854) incluye la verificación posterior. El [reporte autenticado](docs/evidence/authenticated-smoke.json) registra cinco respuestas HTTP 200. Ver también [`docs/bootstrap-evidence.md`](docs/bootstrap-evidence.md). Revisar [`cicd/bootstrap.md`](cicd/bootstrap.md) para el procedimiento reproducible y [`docs/costs.md`](docs/costs.md) para costos.

GitHub Actions ejecuta pruebas Go, build Linux/amd64, escaneo de imagen, validación/pruebas Terraform y escaneo del repositorio en push/PR. El despliegue está temporalmente limitado a `workflow_dispatch` con `deploy=true` con publicación, plan y aplicación en roles separados. Ver [`docs/iam-oidc.md`](docs/iam-oidc.md) para configuración y límites. Requiere revisión del plan y un entorno `production` protegido con aprobación. Los roles y entornos ya están configurados para este repositorio. En un fork deben configurarse nuevamente; las políticas de `iac/identity` están acotadas a la cuenta y al laboratorio actuales.

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
- Cognito, JWT con scope, logs y alarmas 5xx están implementados. El laboratorio no tiene tracing, adaptador de métricas reales ni destino de notificación para alarmas. No se usa API key como mecanismo de autenticación. Ver `docs/architecture.md`.
- La automatización es demostrativa; añadir análisis de políticas, gates de SLO post-deploy, SBOM, signing y validaciones de drift antes de operar una plataforma enterprise.

## Documentación y evidencias

- [Cómo ejecutar y probar](run.md).
- [Checklist frente al PDF](docs/audit.md).
- [Historial del despliegue y límites comprobados](docs/deployment-progress.md).

Solo está desplegado el entorno `lab` en `us-east-1`. Los nombres de entornos GitHub `production` y `production-plan` identifican gates del pipeline; no acreditan una plataforma enterprise ni un segundo entorno AWS.

Pruebas de cierre: [resultados medidos y alcance](docs/validation-results.md), [preparación de producción](docs/production-readiness.md) y [resumen técnico](docs/delivery-summary.md).

Prueba posterior de capacidad: [escalones AWS y diagnóstico](docs/capacity-results.md). El generador regional completó 10.000 RPS por un minuto, sin errores ni descartes. Los intentos anteriores en el Mac se conservan como historial. Ver [correspondencia con el diagrama original](docs/architecture-compliance.md) para elementos opcionales no desplegados.
