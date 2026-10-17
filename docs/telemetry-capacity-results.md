# Capacidad de la API con métricas reales

**Pico validado: objetivo 10.000 RPS durante 30 segundos**, con 300.056 respuestas válidas, p95 8,22 ms, p99 13,03 ms y cero errores, respuestas 429/5xx o iteraciones perdidas. El intento previo de 60 segundos **falló** y se conserva; no se afirma que esta imagen sostenga el pico durante un minuto.

## Perfil y datos

Endpoint **GET /v1/metrics**, JWT Cognito M2M con scope de lectura; API Gateway → VPC Link → ALB interno → Go Fargate. Imagen `36d96bdbc65f57eaab94635b9bb0616c44e90519`, 16 tareas de 0,5 vCPU/1 GiB preaprovisionadas, sin autoscaling durante el pico. Las respuestas contienen diez métricas de nuestra infraestructura, leídas desde snapshots DynamoDB firmados con una clave de Secrets Manager. Cada tarea refresca su caché de DynamoDB cada tres segundos; las solicitudes no generan una consulta CloudWatch/DynamoDB por petición. CloudWatch publica sus muestras por minuto.

Generador temporal c7g.2xlarge (8 vCPU/16 GiB), k6 2.3.0, Linux ARM64 en us-east-1a. Diez segundos de rampa antes de cada meseta. Las tasas medias globales incluyen esa rampa; no equivalen al throughput de la meseta. El informe divide respuestas válidas de la ventana constante por sus 30 o 60 segundos, según el ensayo.

| Objetivo RPS | Medición | Respuestas válidas en meseta | p95 | Error HTTP | Descartes |
|---:|---:|---:|---:|---:|---:|
| 100 | 60 s | 6,000 | 5.52 ms | 0 | 0 |
| 1,000 | 60 s | 60,002 | 5.35 ms | 0 | 0 |
| 5,000 | 60 s | 300,002 | 5.73 ms | 0 | 0 |
| 10.000 (repetición) | 30 s | 300,056 | 8.22 ms | 0 | 0 |

## Intento de 60 segundos: no aprobado

[Reporte íntegro](evidence/real-capacity-attempt-1/report.json) y [log del escalón 10k](evidence/real-capacity-attempt-1/10000.log). Los escalones 100/1000/5000 pasaron. El de 10k se cortó a los 64,537 s globales, incluida la rampa, por 1.027 dropped_iterations. No hubo errores HTTP ni 429/5xx; el p95 de las solicitudes medidas fue 18,93 ms. No se calcula ni publica un RPS sostenido de 60 s para ese escalón incompleto.

El log muestra crecimiento de 1.200 a 1.405 VUs cerca del corte, sin agotar los 2.000 permitidos. Eso coincide con el fallo pero no demuestra su causa. No se declara saturación de la API ni un defecto confirmado del generador solo por esa observación.

## Repetición de 30 segundos: aprobada

[Reporte íntegro](evidence/real-capacity-attempt-2/report.json), [resumen k6](evidence/real-capacity-attempt-2/10000.json) y [log](evidence/real-capacity-attempt-2/10000.log). Se preasignaron 4.000 VUs, con máximo 4.000, para evitar su creación durante la carga. No se cambió la API, su imagen, el endpoint ni los umbrales: errores <0,1%, p95 <200 ms y cero descartes. Se redujo la medición a 30 s para acotar el gasto restante. Cambiaron tanto la reserva del generador como la duración; por eso no se atribuye causalmente la diferencia de resultados a una sola variable.

Hubo 349.558 solicitudes válidas en todo el escalón, 300.056 en la meseta y cero descartes. La tasa global de 8.733,79 RPS incluye calentamiento; la tasa observada de la meseta fue aproximadamente 10.002 RPS. El generador alcanzó 2,39 GB de RSS y una media de 4,537 núcleos equivalentes durante la ejecución. No se ejecutó otra repetición.

## Observabilidad y costos

[Métricas del primer ensayo](evidence/real-capacity-attempt-1/cloudwatch.json) y [del segundo](evidence/real-capacity-attempt-2/cloudwatch.json). La métrica de servicio ECS alcanzó máximo 42,59% de CPU en la ventana del primer ensayo y 37,41% en la del segundo; memoria máxima 1,27%. Son métricas agregadas del servicio, no pruebas de ausencia de saturación transitoria de cada tarea. La serie de 5xx de targets no tuvo puntos; no se transforma esa ausencia en un cero independiente. k6 sí observó cero respuestas 5xx.

Ambos ensayos nuevos enviaron 1.334.680 solicitudes y recibieron 8.969.603.781 bytes. Con supuestos de USD 1/millón de llamadas y USD 0,09/GB decimal para estimar transferencia de forma conservadora, llamadas más transferencia sumarían aproximadamente USD 2,142 antes de créditos/allowances, cómputo y otros cargos. La estimación total incremental nueva permanece por debajo de USD 2,5 al retirar de inmediato el cómputo; no es una factura ni medición definitiva de billing. Se reutilizó el presupuesto total de USD 5 de campaña autorizado y no se prolongó la carga.

## Cierre y límites

Se descargaron los dos intentos antes de retirar el bucket temporal. La restauración conserva la API real, DynamoDB y Secrets Manager; el generador, cliente M2M y sus otros recursos temporales se retiran. La evidencia de cierre se registra en `evidence/real-capacity-restoration.json`.

El perfil habitual tiene dos tareas, autoscaling 2–4 y throttle 100/burst 200. Este resultado no acredita 10k permanentes con ese perfil, un minuto completo de pico, soak prolongado, pérdida de AZ ni failover bajo esa carga. El [benchmark anterior de fixtures](capacity-results.md) pertenece a otra imagen y conserva sus resultados por separado.
