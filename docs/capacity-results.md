# Resultado de capacidad: pico de 10.000 RPS validado

El 16 de octubre de 2026 se completaron todos los escalones regionales hasta **10.000 RPS** sobre `GET /v1/services`, con JWT Cognito y fixtures. En el minuto de medición de 10k se recibieron **600.002 respuestas válidas**, media **10.000,03 RPS**, **p95 9,05 ms**, **p99 21,87 ms**, sin errores HTTP, 429, 5xx ni iteraciones descartadas.

## Resultados regionales

Cada escalón incluye 10 s de calentamiento y una meseta independiente de 60 s. Las cifras siguientes corresponden a la meseta; la tasa global de k6 incluye calentamiento y por eso es menor que el objetivo. Cada iteración realiza una única solicitud: aquí RPS no representa una transacción de negocio de varias llamadas.

| Objetivo RPS | Respuestas válidas / 60 s | RPS válidos medidos | p95 ms | p99 ms | Errores HTTP | Descartes k6 |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 6,000 | 100.00 | 6.80 | 9.93 | 0% | 0 |
| 500 | 30,001 | 500.02 | 5.86 | 9.65 | 0% | 0 |
| 1,000 | 60,001 | 1,000.02 | 5.60 | 8.38 | 0% | 0 |
| 2,500 | 150,001 | 2,500.02 | 5.66 | 8.86 | 0% | 0 |
| 5,000 | 300,005 | 5,000.08 | 5.52 | 10.10 | 0% | 0 |
| 10,000 | 600,002 | 10,000.03 | 9.05 | 21.87 | 0% | 0 |

La secuencia completa envió **1.241.329 solicitudes**, todas válidas. Evidencias originales: [report.json](evidence/regional-capacity/report.json), resúmenes y logs por escalón en el mismo directorio, y [CloudWatch](evidence/regional-capacity/cloudwatch.json).

## Entorno y autenticación

- Generador temporal EC2 c7g.2xlarge: ocho vCPU, 16 GiB, Amazon Linux ARM64 en us-east-1a, k6 oficial 2.3.0 (e088784614). Sin ingreso/SSH; administración SSM, EBS cifrado e IMDSv2.
- API: misma imagen previamente desplegada `6cc31df8eadeeb888122a90e5503350f8478688f`, 16 tareas Fargate preaprovisionadas de 0,5 vCPU/1 GiB. Min y max fijados a 16 para aislar capacidad del retraso del autoscaler.
- Tráfico público HTTPS real: API Gateway HTTP API → JWT authorizer → VPC Link → ALB interno → Fargate privado. No se midió acceso directo al ALB ni se deshabilitó autenticación.
- Autenticación M2M con cliente temporal, issuer del pool existente y scope infra-metrics/read. El authorizer aceptó temporalmente ese client_id además del consumidor humano. Se obtuvo un token por escalón; no hubo login interactivo durante la secuencia.
- Secretos/JWT solo se capturaron en memoria del driver, nunca en reportes, user data ni parámetros SSM. El client secret fue atributo sensible del estado Terraform remoto cifrado; el cliente temporal se eliminó al finalizar y los roles CI no tienen acceso a ese key de estado.

La mayor demanda de CPU media medida del generador fue 2,659 equivalentes de núcleo y su máximo RSS reportado 697.810.944 bytes. En la ventana CloudWatch, CPUUtilization del servicio tuvo un máximo observado de 32,43 % y MemoryUtilization de 0,68 %; TargetResponseTime máximo observado 205,71 ms. Son métricas agregadas por minuto; no equivalen al p95/p99 de cliente. No hubo puntos de HTTPCode_Target_5XX_Count en la consulta: el cero de 5xx observado procede del contador k6.

## Restauración y costo

Terraform restauró min=2/max=4, throttle=100/burst=200 y la audiencia original. Se retiraron **los 14 recursos temporales**, incluida instancia, cliente M2M, rol, perfil, launch template y bucket. Evidencias: [regional-cleanup.json](evidence/regional-capacity/regional-cleanup.json). El plan posterior terminó con No changes y el smoke de readiness/rechazo sin token pasó. El laboratorio no se deja abierto permanentemente a 10k RPS por costo.

Tarifa EC2 consultada: USD 0,29/h. Los dos intentos del Mac sumaron 462.043 solicitudes; junto con la secuencia regional suman 1.703.372, equivalentes a ≈USD 1,703 en llamadas Gateway a USD 1/millón, antes de créditos y otros cargos. Es estimación de ese componente, no una factura. El presupuesto incremental total autorizado fue USD 5; se retiró el generador y se revirtió la capacidad adicional para limitar consumo.

## Interpretación y límites

Este resultado demuestra el pico medido de un endpoint de fixtures durante un minuto, con el perfil regional descrito. No prueba 10k sostenidos durante horas, consultas a datos reales, toda mezcla de endpoints, pérdida de AZ bajo 10k ni escalamiento automático desde dos tareas ante un pico instantáneo. La recuperación de una tarea y el rollback de revisión con imagen idéntica se probaron por separado y a carga baja; ver [validation-results.md](validation-results.md). Las alarmas básicas no tienen destinatario de notificación.

Los intentos iniciales en macOS se conservaron, incluso los cortes por dropped_iterations: [historial local](capacity-local-attempts.md). La región, plataforma, build de k6, latencia y autenticación cambiaron en la prueba regional. Que esta pasara no demuestra por sí solo la causa exacta de los descartes locales.

Los bonus continúan fuera de esta fase. No hubo WAF, canary/blue-green ni tracing nuevos.
