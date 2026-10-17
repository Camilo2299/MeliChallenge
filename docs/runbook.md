# Operación del laboratorio

Antes de operar, confirmar perfil, cuenta, región y entorno; no usar root. La API AWS usa datos reales; el modo local conserva fixtures. Nunca imprimir JWT, passwords o secretos.

## Diagnóstico

1. Probar API Gateway /health/ready. Para negocio, usar access token con scope infra-metrics/read.
2. Inspeccionar errores de integración en /apigateway/infra-signal-lab y eventos ECS.
3. Verificar targets ALB, tasks running/desired, salida NAT, pull de ECR, roles de ejecución y logs /ecs/infra-signal-lab.
4. Separar 401/403 de JWT/scopes, 429 de throttling y 5xx de integración/backend. El smoke sin token solo prueba rechazo, no autenticación completa.

## Rollback

Ensayo realizado: ver validation-results.md. Para un incidente real, usar cicd/rollback.sh únicamente con ARN anterior comprobado, activo y autorización; definir AWS_REGION, CLUSTER, SERVICE y PREVIOUS_TASK_DEFINITION_ARN explícitamente. Las revisiones retiradas por Terraform no se pueden usar directamente para desplegar; revisar y volver a registrar su configuración conocida antes de elegirlas como destino. Luego reconciliar image_tag con la versión elegida en Terraform y revisar el plan; de lo contrario el siguiente apply deshará el rollback. El circuit breaker cubre fallos de arranque/health, no todas las regresiones.

## Desmontaje seguro

No se ha ejecutado destrucción. Para retirar el laboratorio con autorización:

1. Guardar outputs, imagen de entrega, evidencias y estado remoto. Revisar los recursos asociados al estado lab; no tocar recursos ajenos.
2. La protección ALB está activa. Preparar un plan con deletion_protection=false y aplicar solo tras revisión/autorización.
3. Generar `terraform -chdir=iac plan -destroy -out=destroy.tfplan`; revisar todo. Ejecutar `terraform -chdir=iac apply destroy.tfplan` únicamente con autorización explícita. Verificar eliminación de NAT, ALB, tareas y liberación de EIP; escala ECS a cero no elimina esos costos.
4. Mantener el bucket de estado, presupuesto y ECR mientras sea necesario entregar/reproducir/volver atrás. Bootstrap tiene estado separado y protección prevent_destroy en el bucket.
5. No vaciar ECR ni quitar protección/vaciar versiones S3 automáticamente. Su eliminación requiere un plan de retención y autorización adicionales. Confirmar ausencia de costos residuales y otras cargas de la cuenta.

AWS Budgets no corta el gasto ni garantiza una alerta instantánea. Consultar docs/costs.md antes de mantener el entorno encendido durante días.

## Telemetría y frescura

Si readiness informa TELEMETRY_UNAVAILABLE o TELEMETRY_STALE, comprobar permisos y conectividad CloudWatch/ECS/DynamoDB, logs `telemetry collection`, la inyección SNAPSHOT_SIGNING_KEY y el registro LATEST. No imprimir el valor del secreto ni payloads de credenciales. No reemplazar datos ausentes con fixtures. El lease puede tardar hasta 55 s en liberarse tras una tarea detenida. Ver [flujo y rotación de clave](telemetry.md).

La protección de borrado también aplica a DynamoDB. El retiro del secreto respeta una ventana de recuperación de siete días; revisar cualquier cambio de retención antes de destruir.
