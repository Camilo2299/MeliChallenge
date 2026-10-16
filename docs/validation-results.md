# Resultados de validación de cierre

**Resultado posterior de capacidad:** pico de 10.000 RPS durante 60 s validado desde Linux regional; ver [capacity-results.md](capacity-results.md). Se conservan debajo las pruebas previas y sus límites históricos.

Pruebas ejecutadas el 16 de octubre de 2026. Cuenta 026249143093, us-east-1, entorno lab. Las tres pruebas AWS se ejecutaron tras autorización explícita del candidato para el alcance y presupuesto incremental de docs/validation-plan.md.

| Prueba | Resultado medido | Evidencia |
|---|---|---|
| Smoke sin token | Readiness 200; negocio sin token 401 | Pipeline 38857181854 y cicd/smoke.sh |
| Cognito + PKCE | Cinco consultas protegidas con HTTP 200 y contenido esperado | [Reporte autenticado](evidence/authenticated-smoke.json) |
| Carga local | 100 RPS configurados, 6.001 solicitudes, 0 errores, p95 3,185 ms, 0 iteraciones descartadas | [Reporte local](evidence/local-load.json) |
| Carga AWS autenticada | 30 RPS configurados, 1.801 solicitudes, 0 errores, p95 143,228 ms, 0 iteraciones descartadas | [Reporte cloud](evidence/cloud-load.json) |
| Reemplazo de una tarea | Recuperación observada en 58,88 s, dos tareas y dos targets saludables; 49 muestras HTTP sin fallos | [Primer intento y recuperación](evidence/task-replacement-attempt.json) |
| Rollback de revisión | Revisión auxiliar 5 estable en 172,70 s; retorno a revisión original 3 en 171,79 s; 272 muestras HTTP sin fallos; baseline_restored=true | [Ensayo de rollback](evidence/rollback-rehearsal.json) |
| Reconciliación IaC | Plan posterior con exit code 0: No changes; revisión e imagen original conservadas | [Plan posterior](evidence/post-drill-plan.json) |
| Monitoreo básico | Eventos reales de Gateway leídos; tres alarmas 5xx en OK; sin destinatarios configurados | [Observabilidad](evidence/observability.json) |
| Cuotas | Gateway 10.000 RPS/burst 5.000; Fargate On-Demand 30 vCPU | [Consulta vigente](evidence/service-quotas.json) |

La latencia cloud incluye el trayecto del cliente macOS a us-east-1. Los conteos de k6 pueden incluir una iteración en el límite temporal. En la exportación legacy de k6, los valores false de thresholds indican que no se violó el umbral; el campo observed.thresholds_passed resume el resultado sin esa ambigüedad.

## Incidente del helper y recuperación

El primer intento recuperó correctamente la tarea detenida, pero el helper falló antes de cambiar la revisión del servicio: el nombre del parámetro Python service colisionaba con el flag --service de ECS. El campo baseline_restored=false de ese reporte reflejaba un flag interno pendiente, no un cambio efectivo de revisión. Una consulta independiente confirmó que el servicio continuaba en infra-signal-lab:3 con dos tareas. Se corrigió el helper, se retiró la revisión auxiliar 4 sin uso y se retomó únicamente el rollback; no se repitieron ni la carga ni la detención de tarea. El segundo reporte registra las transiciones 3 → 5 → 3, y la revisión auxiliar 5 se retiró al finalizar. Se conserva el primer reporte para no ocultar el fallo.

## Interpretación y límites

- 100 RPS locales y 30 RPS cloud no acreditan 10.000 RPS. No se ejecutaron escalones de alta carga, soak ni comparación Python/Go.
- La recuperación prueba pérdida de una tarea, no caída completa de una AZ. Las dos tareas estaban inicialmente en us-east-1a y us-east-1b.
- El rollback usa la misma imagen/configuración bajo una revisión distinta. Valida el procedimiento de despliegue y retorno; no detecta una regresión funcional ni ejercita el circuit breaker con una imagen defectuosa.
- Las muestras aproximadamente cada segundo no pueden descartar interrupciones entre muestras. No equivalen a un SLO de largo plazo.
- La aplicación entrega fixtures; no consulta métricas reales de infraestructura.
- No se prueba envío de alertas: las alarmas no tienen destinatario y los presupuestos no apagan recursos.

Ver [alcance de producción](production-readiness.md), [checklist del PDF](audit.md) y [resumen de entrega](delivery-summary.md).

## Validación de los helpers

Tres tests locales del helper pasaron: construcción de update-service, retorno a baseline en transición exitosa y restauración/registro del fallo ante un candidato que no estabiliza. Los dos últimos usan AWS simulado y no sustituyen los ensayos reales. Se incorporan a CI junto con compilación Python y validación de sintaxis shell.

## Intento posterior hacia 10k RPS

Ver [capacity-results.md](capacity-results.md): se validaron escalones completos hasta 2.500 RPS durante un minuto. En 5k hubo 59 iteraciones descartadas y se abortó sin errores HTTP; no se ejecutó el escalón de 10k. Se restauró la configuración habitual. Esto amplía la evidencia de carga, pero no cierra el objetivo de 10k RPS.

## Cierre regional: pico solicitado completado

La fase regional posterior completó 100/500/1k/2,5k/5k/10k RPS, con 60 s por meseta. En 10k: 600.002 respuestas válidas, 10.000,03 RPS, p95 9,05 ms y p99 21,87 ms; cero errores, 429, 5xx y descartes. Ver [capacity-results.md](capacity-results.md). Este resultado reemplaza la conclusión de capacidad pendiente de los intentos locales anteriores, que se conservan como historial. Los límites de soak, datos sintéticos, fallo AZ y bonus permanecen.
