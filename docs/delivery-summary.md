# Resumen técnico de la solución

## Qué está demostrado

- API REST Go, endpoints, errores, health checks, Docker/Compose y tests.
- Terraform para networking, ALB interno, Fargate privado multi-AZ, IAM, Cognito y observabilidad básica; estados separados en S3.
- GitHub Actions: build/test, análisis, imagen, ECR, plan revisable, apply protegido y smoke. El inicio del deploy y su aprobación son manuales; las etapas posteriores están automatizadas.
- Login humano PKCE y cinco consultas autenticadas; rechazo sin JWT.
- Pico regional: 600.002 respuestas válidas en 60 s, 10.000,03 RPS, p95 9,05 ms, p99 21,87 ms, sin errores, 429, 5xx ni dropped_iterations.
- Recuperación de una tarea y rollback operacional de revisión con imagen idéntica, por separado y con carga baja.
- Laboratorio restaurado y 14 recursos del generador retirados; evidencias y límites en capacity-results.md y validation-results.md.

## Límites de validación

El dato es sintético. No se probó soak largo, pérdida de AZ bajo 10k, regresión funcional/circuit breaker ni operación de alertas con notificación. Solo lab está desplegado. La capacidad del pico requirió 16 tareas preparadas: el perfil habitual queda en 2–4 tareas y throttle 100 para limitar costos. WAF, canary/blue-green y tracing avanzado son bonus, se revisan aparte.
