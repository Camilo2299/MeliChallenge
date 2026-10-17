# Alcance de la entrega y preparación para producción

La entrega es un laboratorio AWS funcional del escenario. El PDF permite elegir dominio y tecnología; la versión AWS actual expone métricas y estado reales de CloudWatch/ECS, persistidos en DynamoDB, mediante Go y REST. La automatización de infraestructura y la autenticación tienen evidencia real. Su aceptación final depende de la evaluación; este documento no certifica capacidad enterprise.

## Qué significa el objetivo de 10k RPS

Consulta de cuotas de cierre: API Gateway en us-east-1 informa 10.000 RPS y burst 5.000 para la cuenta; Fargate On-Demand informa 30 vCPU. Ver `evidence/service-quotas.json`. Son cuotas, no throughput medido ni recursos reservados. La cuota regional de API Gateway es compartida; trabajar justo al límite no deja margen para otras APIs o variación del tráfico.

El stage lab limita a 100 RPS/burst 200 y ECS tiene 2–4 tareas de 0,5 vCPU/1 GiB. Esa configuración habitual no acepta 10.000 RPS. Con 16 tareas temporales, la versión real completó 5k/60 s y 10k/30 s; el intento real de 10k/60 s tuvo descartes. Ver [telemetry-capacity-results.md](telemetry-capacity-results.md). El benchmark histórico con fixtures completó 10k/60 s y se conserva por separado en [capacity-results.md](capacity-results.md). Para sostener y ampliar esa validación:

1. Acordar payload, rutas, autenticación, mezcla de requests y SLO; medir también frescura y fallos de la fuente de los datos reales conectados.
2. Benchmark por tarea con la misma imagen/runtime de AWS y nivel de concurrencia; observar CPU, memoria, latencia y límites de conexiones. No extrapolar el resultado loopback de un Mac al trayecto Gateway/ALB/Fargate.
3. Dimensionar tareas preaprovisionadas y límite máximo con margen y capacidad de pérdida de una AZ. No confiar en que el autoscaling alcance un pico instantáneo.
4. Revisar cuotas compartidas y solicitar margen por encima del pico, si corresponde. Ajustar throttle y compute mediante un plan Terraform revisado; revisar conexiones ALB/VPC Link y costos por volumen.
5. Generar carga desde clientes con capacidad comprobada: tramos 100/500/1k/5k/10k, detener ante errores o saturación, registrar throughput realmente entregado, p95/p99, 429/5xx, tareas, scale lag y costo. Las etapas y duraciones necesitan autorización independiente.
6. Tras superar los escalones, realizar soak, pérdida de tarea/AZ y rollback con carga representativa. Conservar resultados, no solo la configuración de k6.

## Otros límites explícitos

- Despliegue y mantenimiento de foundation se verificaron por Actions; destruir/recrear la aplicación aún no se ha ensayado. Se conserva la base S3/ECR/OIDC/roles/presupuesto; la raíz de confianza requiere identidad externa.

- El muestreo durante reemplazo de una tarea no acredita tolerancia a pérdida completa de zona.
- Un ensayo de volver a una revisión saludable con la misma imagen comprueba el procedimiento, no la detección automática de regresiones ni el circuit breaker ante una imagen defectuosa.
- Logs y alarmas básicos no equivalen a guardia operativa. Falta notificación confirmada y prueba de alertas, SLI/SLO medidos y tracing cuando ayude al diagnóstico.
- Solo lab está desplegado. Staging/prod separados, promoción por digest, políticas de emergencia y datos sintéticos son mejoras pendientes.
- No se incluyen WAF ni blue/green/canary; el PDF los enumera como bonus. Se usa throttling y rolling deployment con circuit breaker.
- Las políticas de CI contienen excepciones documentadas y ARN de esta cuenta. Una cuenta diferente requiere revisión; no copiar estos permisos como plantilla universal.

## Criterio para enviar

Se puede presentar el repositorio como implementación funcional, con evidencia y brechas explícitas. Se puede afirmar el pico medido de 10k RPS de métricas reales durante 30 s con 16 tareas, respaldado por [telemetry-capacity-results.md](telemetry-capacity-results.md). El intento real de 60 s falló por descartes. No se debe presentarlo como garantía enterprise de todas las cargas ni como resiliencia bajo ese pico: faltan soak, fallo de AZ y las mejoras operativas indicadas.
