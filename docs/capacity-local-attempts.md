> Historial de los intentos en macOS, previo al resultado regional exitoso. Para el benchmark regional histórico de fixtures ver [capacity-results.md](capacity-results.md); para la versión real vigente ver [telemetry-capacity-results.md](telemetry-capacity-results.md).

# Intento de capacidad hacia 10.000 RPS

Pruebas AWS del 16 de octubre de 2026, autorizadas con presupuesto incremental total de USD 5 y criterios de corte explícitos. Se usó el endpoint GET /v1/services, con fixtures y JWT Cognito, atravesando HTTPS → HTTP API → VPC Link → ALB interno → Fargate. No se ejecutaron bonus adicionales.

## Perfil y resultados

Terraform modificó temporalmente solo el stage (10.000 RPS/burst 5.000) y autoscaling (8–16 tareas de 0,5 vCPU/1 GiB). Se comprobaron ocho tareas y ocho targets saludables antes de cada intento. El generador fue k6 2.3.0 en un Mac ARM64 de 8 GiB/ocho núcleos. La imagen de la API fue la previamente desplegada, 6cc31df8eadeeb888122a90e5503350f8478688f.

| Objetivo | Meseta de 60 s completada | RPS válidos en la meseta | p95 / p99 de meseta (ms) | Errores HTTP | Iteraciones descartadas |
|---:|---|---:|---:|---:|---:|
| 100 | Sí | 100,00 | 83,52 / 87,98 | 0 | 0 |
| 500 | Sí | 500,00 | 84,10 / 88,74 | 0 | 0 |
| 1.000 | Sí | 1.000,02 | 84,82 / 89,34 | 0 | 0 |
| 2.500 | Sí | 2.500,00 | 84,29 / 87,19 | 0 | 0 |
| 5.000 | No; se abortó a los 44,11 s totales, incluido calentamiento | No acreditado como meseta completa | 84,59 / 88,88 para las muestras parciales | 0 | 59 |
| 10.000 | No ejecutado por el corte anterior | No medido | No medido | No medido | No medido |

En el escalón abortado de 5k se recibieron **194.350 respuestas válidas, sin 429 ni 5xx**. No se completó su minuto a tasa objetivo. No usar el campo steady_observed_rps=2822,83 del reporte original como throughput real del intervalo parcial: el helper inicial dividía el contador entre los 60 s previstos aunque se abortara antes. Se conservó el reporte original, y el helper ahora devuelve null para ese cálculo si el escalón falla. El throughput global, que incluye calentamiento y corte, tampoco equivale al throughput de una meseta completa.

Evidencias originales: [repetición](evidence/capacity-retry/report.json) y sus resúmenes por escalón, [primer intento](evidence/capacity-attempt-1/report.json), [CloudWatch](evidence/capacity-cloudwatch.json) y [muestras de tareas](evidence/capacity-task-samples.json).

## Primer intento y corrección del generador

La primera secuencia se detuvo en 100 RPS tras 12,15 s: 1.185 respuestas válidas, cero errores, seis dropped_iterations. Se restauró el perfil original y se pidió autorización para una repetición dentro del mismo presupuesto total. La repetición agregó 10 s de calentamiento por escalón y al menos 100 VUs preasignados; mantuvo los mismos límites de error, latencia y cero dropped_iterations. La evaluación de corte comienza a los 20 s para contar con muestras posteriores al calentamiento. No se relajaron umbrales para ocultar los descartes.

## Diagnóstico: lo que permiten concluir los datos

- La prueba encontró iteraciones que k6 no llegó a iniciar, no errores de las solicitudes enviadas. Eso puede implicar disponibilidad de VUs, planificación del cliente, duración de iteraciones u otros límites; no demuestra por sí solo la capacidad máxima del backend.
- El máximo de RSS registrado del generador fue 383.762.432 bytes y su consumo medio de CPU medido por escalón quedó por debajo de un equivalente de núcleo. No se alcanzaron los cortes propuestos de 2 GiB/seis núcleos, y no sería correcto afirmar saturación de CPU o memoria del Mac como causa establecida.
- La CPUUtilization del servicio ECS tuvo un máximo observado de 27,90 %; MemoryUtilization, 0,68 %. TargetResponseTime tuvo un máximo observado de 46,62 ms en la ventana consultada. Las métricas se agregan a 60 s y no descartan picos más breves ni explican por sí solas el descarte.
- Las muestras de tareas muestran ocho deseadas y ocho ejecutándose, sin pendientes; no se observó una subida de 8 a 16 en esa muestra. El aumento inicial de 2 a 8 fue por el mínimo temporal, no prueba de reacción autónoma del autoscaler a un pico.
- CloudWatch no devolvió puntos de HTTPCode_Target_5XX_Count en esa consulta; no convertir ausencia de puntos en una medición independiente de cero. El contador cero de 5xx proviene de k6.
- Hubo 462.043 solicitudes entre ambos intentos. A USD 1/millón, ≈USD 0,462 solo en llamadas Gateway antes de créditos y otros cargos. Es una estimación del componente, no lectura de factura.

## Cierre y siguiente paso

Se restauraron mediante Terraform min=2/max=4 y throttle=100/burst=200, conservando la imagen original. El plan posterior y la salud final se documentan en evidence/capacity-restoration.json. Por protección de costos, el endpoint no queda habilitado permanentemente a 10k tras esta prueba.

El máximo escalón completo validado es **2.500 RPS durante un minuto**, con la ruta/datos/entorno indicados. No se ha demostrado el pico de 10.000 RPS. Para seguir, aislar el generador en Linux y preferiblemente dentro de us-east-1, verificar su capacidad de entregar la tasa y repetir con un plan y presupuesto revisados. Esto sería otra fase de pruebas, no un bonus; no se aprovisionó un generador regional ni se ejecutó una tercera secuencia.
