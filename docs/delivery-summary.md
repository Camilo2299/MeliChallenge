# Resumen técnico de la solución

> Alcance de versión: los resultados de capacidad con fixtures pertenecen a la imagen anterior. La ampliación de telemetría real está documentada en [telemetry.md](telemetry.md); no extrapolar el benchmark sin repetirlo.

## Qué está demostrado

- API REST Go, endpoints, errores, health checks, Docker/Compose y tests. En AWS expone métricas reales y snapshots DynamoDB; vista /dashboard con Cognito.
- Terraform para networking, ALB interno, Fargate privado multi-AZ, IAM, Cognito y observabilidad básica; estados separados en S3.
- GitHub Actions: build/test, análisis, imagen, ECR, plan revisable, apply protegido y smoke. El inicio del deploy y su aprobación son manuales; las etapas posteriores están automatizadas.
- Login humano PKCE de la versión anterior; nueva versión validada con siete consultas M2M, dos recolecciones sucesivas y 30 RPS/60 s sin errores. Rechazo sin JWT.
- Pico de la versión real: 300.056 respuestas válidas en 30 s en /v1/metrics, p95 8,22 ms y p99 13,03 ms, sin errores, 429, 5xx ni dropped_iterations. El intento real de 60 s falló por descartes; se conserva por separado, al igual que el histórico de fixtures.
- Recuperación de una tarea y rollback operacional de revisión con imagen idéntica, por separado y con carga baja.
- Laboratorio restaurado y 14 recursos del generador retirados; evidencias y límites en capacity-results.md y validation-results.md.

## Límites de validación

El modo local usa datos sintéticos; AWS consulta datos reales. El benchmark anterior de 10k/60 s pertenece a fixtures. Esta imagen validó 10k/30 s; el intento de 60 s falló por descartes. Ver telemetry-capacity-results.md. No se probó soak largo, pérdida de AZ bajo 10k, regresión funcional/circuit breaker ni operación de alertas con notificación. Solo lab está desplegado. La capacidad del pico requirió 16 tareas preparadas: el perfil habitual queda en 2–4 tareas y throttle 100 para limitar costos. WAF, canary/blue-green y tracing avanzado son bonus, se revisan aparte.
