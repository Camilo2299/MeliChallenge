# Checklist de entrega frente al challenge

> Alcance de versión: los resultados de capacidad con fixtures pertenecen a la imagen anterior. La telemetría real y sus mediciones posteriores están documentadas en [telemetry.md](telemetry.md) y [telemetry-capacity-results.md](telemetry-capacity-results.md); los resultados históricos no se extrapolan.

Actualizado el 17 de octubre de 2026 (UTC) tras contrastar el PDF original y el despliegue real. La implementación usa Go por elección explícita del candidato. Este checklist distingue implementación, evidencia y brechas; no equivale a certificar una operación enterprise.

| Requisito del PDF | Estado | Archivo / evidencia | Forma de comprobar o pendiente |
|---|---|---|---|
| API REST, al menos tres endpoints | Implementado y probado | `api/main.go`, `api/main_test.go`, `docs/evidence/authenticated-smoke.json` | Inventario, detalle, despliegues, resumen, métricas e histórico; siete consultas reales autenticadas 200 (evidence/real-telemetry.json) |
| Errores consistentes y validación | Implementado; probado en tests | `api/main_test.go`, contrato OpenAPI | 404/405/422 y JSON uniforme del backend; Gateway tiene sus propios errores |
| Health check | Probado en AWS | `cicd/smoke.sh`, pipeline exitoso | Readiness AWS verifica snapshot reciente; liveness interna independiente de AWS |
| Docker run / Compose | Implementado y validado en CI | `api/Dockerfile`, `docker-compose.yml`, `docs/local-validation.md` | Binario estático, scratch, no-root; runtime Fargate Linux/amd64 |
| Sin credenciales hardcodeadas | Implementado | `.gitignore`, roles OIDC, `iac/identity/` | Acceso humano SSO y CI OIDC; IDs/ARN de cuenta no son secretos |
| Exposición pública segura | Probado en AWS | `iac/gateway.tf`, reporte autenticado, smoke | HTTPS público, JWT y scope; sin token 401; datos reales autenticados 200 |
| Alta disponibilidad y tolerancia a fallos | Topología y mecanismos configurados | `iac/main.tf`, `docs/architecture.md` | ALB/subredes en dos AZ, dos tareas, NAT por AZ, health checks y circuit breaker; reemplazo de una tarea probado en 58,88 s; falta pérdida de AZ |
| Escalabilidad para 10k RPS | Pico regional validado; alcance limitado | `iac/main.tf`, `docs/loadtest.js`, `docs/costs.md` | Versión real con 16 tareas: 5k/60 s y 10k/30 s; 10k/60 s falló por descartes. Histórico fixtures 10k/60 s separado. Falta soak/fallo AZ; ver telemetry-capacity-results.md |
| Manejo de secretos | Integrado y probado en AWS | Roles ECS, variable `secret_arn` | Clave HMAC en Secrets Manager inyectada por execution role; snapshots verificados; secreto write-only sin valor en estado |
| Monitoreo básico | Configurado; smoke probado | Logs app/Gateway, Container Insights y alarmas en `iac/` | Eventos Gateway verificados y alarmas OK; faltan destino de notificación, tracing y pruebas de alertas |
| Diagrama y decisiones | Entregado | `docs/architecture.md`, README | Mermaid del camino HTTP API → VPC Link → ALB privado → Fargate |
| Build, tests y calidad/seguridad | Ejecutado en CI | `.github/workflows/deploy.yml` | Go fmt/race/cover/vet, Docker, Trivy y Terraform validate/mock tests |
| Push a registry y despliegue automático | Ejecutado desde push main con gate de entorno | [Run exitoso](https://github.com/Camilo2299/MeliChallenge/actions/runs/39001245527) | Verify → Publish → plan/apply → smoke; LAB_AUTODEPLOY_ENABLED=true habilita autodeploy; lifecycle/foundation operan por Actions |
| Estrategia de rollback | Ensayo operacional realizado; alcance limitado | Circuit breaker ECS, `cicd/rollback.sh`, `docs/runbook.md` | Retorno 3 → 5 → 3 con imagen idéntica, 272 muestras sin fallos; no prueba regresión ni circuit breaker |
| IaC networking, compute, LB, IAM, observabilidad | Aplicada | `iac/`, `iac/bootstrap/`, `iac/identity/`, `iac/control/` | Estados separados S3 con bloqueo; foundation por Actions; raíz de confianza inicial externa. Destroy-plan ejecutado; ciclo destruir/recrear no ensayado |
| Estructura /api, /iac, /cicd y README/run | Entregado | Directorios raíz, `README.md`, `run.md` | Instrucciones locales, despliegue y demo |
| Uso de IA transparente | Entregado | `prompts.md` | Apoyo en implementación/documentación; validación contra pruebas y AWS real |

## Funcionalidades adicionales y límites

| Tema | Situación y límite |
|---|---|
| Autoscaling | CPU y requests por target configurados; carga autenticada de 30 RPS probada; respuesta del autoscaling a saturación no medida |
| WAF / rate limiting | Throttling de HTTP API configurado. WAF no desplegado; HTTP API no tiene asociación WAF directa en este diseño |
| Blue/green o canary | No implementado; rolling deployment con circuit breaker |
| Observabilidad sólida | Base implementada; faltan SLI/SLO medidos, notificaciones y tracing |
| Tests automatizados | Go, Terraform y smoke del pipeline; login interactivo con PKCE ejecutado por el candidato |
| Multiambiente | Solo lab desplegado. Propuesta: cuentas/estados/roles aislados, misma imagen por digest y fixtures en staging; no declarar paridad probada |
| Costos | Estimación y supuestos en `docs/costs.md`; presupuesto USD 80 sin corte automático. No confundir estimación con factura real |
| Gobierno de cambios | Plan guardado y aprobación del entorno production; procedimiento de emergencia y reconciliación en runbook |

La versión AWS actual expone datos reales de CloudWatch/ECS, persistidos en DynamoDB; el modo local mantiene fixtures. La cobertura funcional y el pico regional no sustituyen seguridad exhaustiva, soak, rollback de una regresión ni fallo de AZ. El pico real de 10k RPS se demostró durante 30 s con 16 tareas preparadas; el intento real de 60 s tuvo descartes. El resultado anterior con fixtures está separado. Siguen pendientes resiliencia bajo ese pico, soak y operación enterprise.

Resultados de cierre y límites: [validation-results.md](validation-results.md). Resumen técnico: [delivery-summary.md](delivery-summary.md).
