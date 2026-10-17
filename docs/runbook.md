# Operación del laboratorio

La operación normal de despliegue, rollback y destrucción usa **Lab lifecycle**; el mantenimiento de S3/ECR/presupuesto e identidad usa **Foundation maintenance**. Ver [lifecycle.md](lifecycle.md). Los comandos AWS/Terraform de este documento son herramientas de diagnóstico o recuperación externa, no el flujo normal de cambios.

Antes de operar, confirmar perfil, cuenta, región y entorno; no usar root. La API AWS usa datos reales; el modo local conserva fixtures. Nunca imprimir JWT, passwords o secretos.

## Diagnóstico

1. Probar API Gateway /health/ready. Para negocio, usar access token con scope infra-metrics/read.
2. Inspeccionar errores de integración en /apigateway/infra-signal-lab y eventos ECS.
3. Verificar targets ALB, tasks running/desired, salida NAT, pull de ECR, roles de ejecución y logs /ecs/infra-signal-lab.
4. Separar 401/403 de JWT/scopes, 429 de throttling y 5xx de integración/backend. El smoke sin token solo prueba rechazo, no autenticación completa.

## Rollback

Ejecutar **Actions → Lab lifecycle → rollback** en `main`. El controlador aplica con Terraform la imagen anterior registrada en el manifiesto privado, espera estabilidad y repite la prueba autenticada. No depende de una task definition histórica retirada. Si aún no existe un despliegue exitoso anterior registrado, el workflow se detiene. ECS conserva además su circuit breaker para fallos de arranque/health; no cubre todas las regresiones.

Los scripts antiguos de rollback por CLI se conservan como referencia de los ensayos históricos. No usarlos como procedimiento normal: pueden dejar drift respecto a Terraform.

## Desmontaje y reconstrucción

Ejecutar primero **Lab lifecycle → destroy-plan** y revisar el inventario. Para borrar, seleccionar `destroy` y confirmar `DESTROY infra-signal-lab DATA`. Se pierden datos de DynamoDB y usuarios de Cognito. El workflow desactiva protecciones de ALB/DynamoDB con un plan dirigido y aplica un nuevo plan de destrucción. Si falla o se interrumpe, repetir `destroy` para completar el estado `destroying`. No lanzar cambios de infraestructura paralelos por CLI.

Se retienen bucket versionado, ECR, presupuesto y confianza OIDC/roles. Para reconstruir la aplicación, seleccionar `deploy`: usa la imagen inmutable y una generación nueva para dominio y secretos. Consultar la URL y secreto de demostración nuevos; los datos anteriores no se restauran. Un push no recrea un laboratorio marcado como ausente.

No se ha ejecutado un ciclo destructivo real durante la instalación. Un plan exitoso no garantiza todos los permisos/tiempos de borrado de AWS. Tampoco borrar la aplicación vacía la cuenta: permanecen la base de control, historial de métricas y secretos pendientes de eliminación. Para modificar o retirar la raíz de confianza usar identidad externa y un plan de retención; la operación normal de la base pasa por **Foundation maintenance**.

AWS Budgets no corta el gasto ni garantiza una alerta instantánea. Revisar [costos](costs.md) antes de mantener el laboratorio encendido durante días. Escalar ECS a cero no elimina el costo de NAT y ALB.

## Telemetría y frescura

Si readiness informa TELEMETRY_UNAVAILABLE o TELEMETRY_STALE, comprobar permisos y conectividad CloudWatch/ECS/DynamoDB, logs `telemetry collection`, la inyección SNAPSHOT_SIGNING_KEY y el registro LATEST. No imprimir el valor del secreto ni payloads de credenciales. No reemplazar datos ausentes con fixtures. El lease puede tardar hasta 55 s en liberarse tras una tarea detenida. Ver [flujo y rotación de clave](telemetry.md).

La protección de borrado también aplica a DynamoDB. El retiro del secreto respeta una ventana de recuperación de siete días; revisar cualquier cambio de retención antes de destruir.
