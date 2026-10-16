# Plan de cierre de validación

Cuenta 026249143093, us-east-1, servicio infra-signal-lab. Preflight de lectura: dos tareas saludables, distribuidas entre us-east-1a y us-east-1b; revisión base infra-signal-lab:3.

## Pruebas preparadas

| Prueba | Acción concreta | Criterio / evidencia |
|---|---|---|
| Carga local | 100 RPS durante 60 s contra localhost:18080 | k6: HTTP 200, contenido válido, errores <0,1%, p95 <200 ms, cero iteraciones descartadas. No mide AWS |
| Carga autenticada AWS | 30 RPS durante 60 s; aproximadamente 1.800 iteraciones (k6 puede incluir una iteración en el límite temporal) | Mismos criterios, JWT solo en memoria; /tmp/meli-cloud-load.json |
| Recuperación de tarea | Detener exactamente una de las dos tareas ECS y esperar reemplazo | Volver a 2 tareas y 2 targets saludables; muestrear GET /v1/services autenticado aproximadamente cada segundo |
| Ensayo de rollback | Registrar revisión nueva con la misma imagen y configuración, desplegarla y volver a la revisión base activa | Estabilidad en ambas transiciones, regreso a revisión original y retiro de revisión auxiliar; /tmp/meli-resilience-drill.json |
| Reconciliación | Plan Terraform posterior usando el tag de la revisión base | Sin cambios inesperados; no cambiar imagen por HEAD documental |

El rollback usa la misma imagen para aislar el procedimiento operacional. No demuestra detección de una regresión funcional ni ejecución del circuit breaker ante una imagen defectuosa. La recuperación de una tarea no equivale a un fallo de zona. El muestreo HTTP no puede descartar interrupciones entre muestras.

`cicd/resilience_drill.py` sin --execute solo consulta el estado. La ejecución necesita aprobación explícita previa. Cada espera de estabilidad tiene timeout de 15 minutos; una recuperación de emergencia puede añadir otro periodo. Se intenta restablecer siempre la revisión inicial y se conserva un reporte sin tokens incluso si falla el ensayo.

## Costos y límites

Estimación, no factura ni corte automático: para 45 minutos, la base documentada es USD 0,1289; dos tareas adicionales durante todo ese periodo sumarían aproximadamente USD 0,0370. Hasta 4.500 solicitudes suman aproximadamente USD 0,0045 de API Gateway, antes de logs, LCUs, almacenamiento y transferencia. Presupuesto incremental propuesto para estos ensayos: USD 1; se espera un consumo menor, pero no existe corte automático que garantice ese monto. No se aumenta el throttle, max_capacity ni se crean NAT/ALB adicionales. Las fuentes y supuestos están en costs.md; tarifas consultadas en https://aws.amazon.com/api-gateway/pricing/ y https://aws.amazon.com/fargate/pricing/.

## Brecha de 10.000 RPS

Este plan no autoriza ni intenta 10k RPS. El laboratorio está limitado a 100 RPS, 2–4 tareas y una cuota Fargate actualizada de 30 vCPU (la consulta inicial había informado 6). Para cerrar ese requisito se necesita otro dimensionamiento, verificación actual de cuotas, presupuesto, cambios Terraform revisados y generadores de carga suficientes. No extrapolar la prueba local o de 30 RPS a esa capacidad.
