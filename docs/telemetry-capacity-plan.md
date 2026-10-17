# Validación de capacidad de la versión con datos reales

Autorización vigente: el usuario autorizó todos los stages de pruebas sin aprobación manual adicional. Se reutiliza el límite incremental total de USD 5 de la campaña; estimación anterior aproximada USD 2–2,5, sin factura definitiva. Esta repetición acotada se estima en hasta USD 2,5 adicionales, con restauración inmediata; no habilita una carga sostenida posterior.

Perfil temporal: 16 tareas existentes, throttle 10k/burst 5k, mismo Go y tabla/secretos, generador EC2 c7g.2xlarge por menos de una hora. Secuencia propuesta: 100, 1.000, 5.000 y 10.000 RPS; 10 s ramp y 60 s medidos por stage. Endpoint **GET /v1/metrics**, JWT M2M con scope; se comprueba origen AWS y diez métricas, sin fixtures. Si el presupuesto estimado al observar tamaño de payload no permite todos los escalones, se reduce la secuencia o se detiene.

Cortes: errores/invalid responses <0,1%, p95 <200 ms, cero dropped_iterations. Detener al primer stage fallido. No simular caída de AZ ni soak. Descargar evidencias; restaurar audiencia humana, min2/max4, throttle100/burst200 y dos tareas; destruir los 14 recursos del generador, conservar DynamoDB/Secrets Manager/API. Comprobar Terraform sin diferencias y smoke.

Las respuestas son más grandes que las de inventario. La prueba anterior de fixtures no se sobrescribe. El historial de métricas y el tamaño observado se registran en las evidencias de esta campaña.

## Repetición acotada tras fallo de generación

Los escalones 100/1000/5000 pasaron 60 s. El de 10k se cortó por 1.027 dropped_iterations, sin HTTP 429/5xx y con p95 18,9 ms; no se aprueba ese intento. El log muestra crecimiento de VUs al final; eso no prueba la causa exacta. Se autoriza por la instrucción vigente una repetición de solo 10k con 10 s de ramp y 30 s de medición, preAllocatedVUs=maxVUs=4000. No cambia la API ni relaja los umbrales. Estimación adicional de esa repetición <USD 0,7, dentro del total de USD 5 de campaña; no es factura. Preservar ambos intentos, limitar el resultado eventual a 30 s y restaurar al finalizar sin otra secuencia.
