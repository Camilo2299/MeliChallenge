# Operación del laboratorio

Antes de operar, confirmar perfil, cuenta, región y entorno; no usar root. La API muestra fixtures. Nunca imprimir JWT, passwords o secretos.

## Diagnóstico

1. Probar API Gateway /health/ready. Para negocio, usar access token con scope infra-metrics/read.
2. Inspeccionar errores de integración en /apigateway/infra-signal-lab y eventos ECS.
3. Verificar targets ALB, tasks running/desired, salida NAT, pull de ECR, roles de ejecución y logs /ecs/infra-signal-lab.
4. Separar 401/403 de JWT/scopes, 429 de throttling y 5xx de integración/backend. El smoke sin token solo prueba rechazo, no autenticación completa.

## Rollback

Usar cicd/rollback.sh únicamente con ARN anterior comprobado y autorización. Luego reconciliar image_tag con la versión elegida en Terraform y revisar el plan; de lo contrario el siguiente apply deshará el rollback. El circuit breaker cubre fallos de arranque/health, no todas las regresiones.

## Desmontaje seguro

No se ha ejecutado destrucción. Para retirar el laboratorio con autorización:

1. Guardar outputs, imagen de entrega, evidencias y estado remoto. Revisar los recursos asociados al estado lab; no tocar recursos ajenos.
2. La protección ALB está activa. Preparar un plan con deletion_protection=false y aplicar solo tras revisión/autorización.
3. Generar `terraform -chdir=iac plan -destroy -out=destroy.tfplan`; revisar todo. Ejecutar `terraform -chdir=iac apply destroy.tfplan` únicamente con autorización explícita. Verificar eliminación de NAT, ALB, tareas y liberación de EIP; escala ECS a cero no elimina esos costos.
4. Mantener el bucket de estado, presupuesto y ECR mientras sea necesario entregar/reproducir/volver atrás. Bootstrap tiene estado separado y protección prevent_destroy en el bucket.
5. No vaciar ECR ni quitar protección/vaciar versiones S3 automáticamente. Su eliminación requiere un plan de retención y autorización adicionales. Confirmar ausencia de costos residuales y otras cargas de la cuenta.

AWS Budgets no corta el gasto ni garantiza una alerta instantánea. Consultar docs/costs.md antes de mantener el entorno encendido durante días.
