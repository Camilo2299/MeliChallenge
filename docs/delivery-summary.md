# Resumen técnico de la solución

> Alcance de versión: los resultados de capacidad con fixtures pertenecen a la imagen anterior. La ampliación de telemetría real está documentada en [telemetry.md](telemetry.md); las mediciones reales posteriores están en [telemetry-capacity-results.md](telemetry-capacity-results.md).

## Qué está demostrado

- API REST Go, endpoints, errores, health checks, Docker/Compose y tests. En AWS expone métricas reales y snapshots DynamoDB; vista /dashboard con Cognito.
- Terraform para networking, ALB interno, Fargate privado multi-AZ, IAM, Cognito y observabilidad básica; estados separados en S3.
- GitHub Actions: build/test, análisis, imagen, ECR, plan revisable, apply protegido y smoke. Push main despliega con `LAB_AUTODEPLOY_ENABLED=true`, conservando aprobación del environment production. Lifecycle y foundation centralizan operación y mantenimiento; la raíz de confianza inicial requiere SSO externo.
- Login humano PKCE de la versión anterior; nueva versión validada con siete consultas M2M, dos recolecciones sucesivas y 30 RPS/60 s sin errores. Rechazo sin JWT.
- Pico de la versión real: 300.056 respuestas válidas en 30 s en /v1/metrics, p95 8,22 ms y p99 13,03 ms, sin errores, 429, 5xx ni dropped_iterations. El intento real de 60 s falló por descartes; se conserva por separado, al igual que el histórico de fixtures.
- Recuperación de una tarea y rollback operacional de revisión con imagen idéntica, por separado y con carga baja.
- Laboratorio restaurado y 14 recursos del generador retirados; evidencias y límites en [telemetry-capacity-results.md](telemetry-capacity-results.md) y [validation-results.md](validation-results.md).

- [Deploy con smoke autenticado exitoso](https://github.com/Camilo2299/MeliChallenge/actions/runs/39001245527) y [mantenimiento foundation exitoso](https://github.com/Camilo2299/MeliChallenge/actions/runs/39000421161).

## Límites de validación

El modo local usa datos sintéticos; AWS consulta datos reales. El benchmark anterior de 10k/60 s pertenece a fixtures. Esta imagen validó 10k/30 s; el intento de 60 s falló por descartes. Ver telemetry-capacity-results.md. El ciclo completo destruir/recrear está preparado pero no ensayado; se retiene la base de control. No se probó soak largo, pérdida de AZ bajo 10k, regresión funcional/circuit breaker ni operación de alertas con notificación. Solo lab está desplegado. La capacidad del pico requirió 16 tareas preparadas: el perfil habitual queda en 2–4 tareas y throttle 100 para limitar costos. WAF, canary/blue-green y tracing avanzado son bonus, se revisan aparte.
