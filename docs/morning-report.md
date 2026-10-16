# Reporte final: pico de 10.000 RPS completado

**Resultado: todos los escalones regionales pasaron.** El endpoint autenticado GET /v1/services completó una meseta de 60 s con 600.002 respuestas válidas: media 10.000,03 RPS, p95 9,05 ms y p99 21,87 ms. Cero errores HTTP, 429, 5xx y dropped_iterations.

La prueba usó k6 oficial Linux ARM64 en un EC2 temporal dentro de us-east-1 y 16 tareas Fargate preparadas. Atravesó el endpoint público API Gateway, JWT Cognito M2M con scope de lectura, VPC Link y ALB interno. No se deshabilitó autenticación ni se accedió directamente al backend. La secuencia completa envió 1.241.329 solicitudes válidas.

## Estado al cerrar

- Se descargaron reportes y logs sin tokens.
- Terraform retiró los 14 recursos auxiliares: generador, cliente M2M, bucket temporal, rol/perfil y demás componentes.
- La API regresó a dos tareas ejecutándose, autoscaling 2–4 y throttle 100/burst 200; conserva la imagen desplegada original y la audiencia del cliente humano.
- El plan posterior no mostró cambios y el smoke de readiness/rechazo sin token pasó.
- No se cambiaron las protecciones de aprobación del pipeline GitHub ni se enviaron mensajes a terceros.

## Evidencias

[Resultados completos y límites](capacity-results.md), [reporte k6](evidence/regional-capacity/report.json), [métricas CloudWatch](evidence/regional-capacity/cloudwatch.json), [retorno y retiro de recursos](evidence/regional-capacity/regional-cleanup.json), [checklist PDF](audit.md) y [resumen técnico](delivery-summary.md).

## Alcance de validación

Se demostró el pico solicitado para el endpoint, fixtures, ventana y perfil medidos. Los intentos del Mac, incluidos los fallos por descartes, se conservaron. No se identificó su causa exacta solo por comparar con Linux regional.

No se validaron soak prolongado, caída de AZ bajo 10k ni integración con métricas reales. La recuperación de tarea y el rollback de revisión con imagen idéntica se verificaron antes a carga baja. Los bonus siguen aparte; las alarmas básicas no tienen notificación configurada.
