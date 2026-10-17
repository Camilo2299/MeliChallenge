# Uso responsable de IA en esta entrega

Se utilizó asistencia de IA para estructurar una propuesta de arquitectura, generar un esqueleto de API Go (`net/http`), pruebas iniciales, Docker, Terraform, CI/CD y documentación. Las decisiones técnicas, validación local, revisión de IAM, revisión de costos cloud, pruebas de carga y verificación del despliegue son responsabilidad del candidato.

## Verificaciones necesarias antes de presentar
- Ejecutar los tests y validar el comportamiento HTTP.
- Ejecutar `terraform fmt`, `terraform init` y `terraform validate` contra la versión correcta del provider.
- Revisar el `terraform plan` completo (incluidos costos, permisos y cambios destructivos).
- Confirmar que la imagen arranca en ECS y que el ALB informa targets healthy.
- Ejecutar k6 con tráfico gradual antes de afirmar 10k RPS sostenidos.

No se presentan como hechas pruebas o despliegues que no se hayan ejecutado. La API entrega información ilustrativa, no datos de infraestructura reales.

## Validación operacional de cierre

La IA ayudó a preparar un generador k6 acotado y un helper de ensayo ECS. Se ejecutaron con autorización explícita: carga autenticada de 30 RPS, reemplazo de una tarea y retorno a una revisión original con la misma imagen. Se detectó y corrigió una colisión de argumentos en el helper; se conserva el reporte del primer intento y la recuperación en docs/validation-results.md. El candidato completó el login interactivo; no se guardaron tokens. Los resultados se contrastaron con ECS, targets ALB y Terraform; no prueban 10k RPS ni pérdida de AZ.

## Prueba regional de pico

Con autorización general de etapas de prueba y presupuesto total de USD 5, se preparó un generador Linux regional mediante Terraform y autenticación Cognito M2M temporal sin intervención humana. No se reutilizó ni cambió la contraseña del candidato. Se conservaron los intentos locales fallidos y se verificaron seis escalones regionales: pico de 10k RPS por un minuto, sin errores/descartes. Se descargaron reportes, se retiraron 14 recursos temporales y se comprobó el retorno a la configuración original. El resultado no se extrapola a datos reales, soak ni pérdida de AZ.

## Ampliación a telemetría real

Se solicitó sustituir fixtures en AWS por métricas de la misma infraestructura y persistencia. Se implementaron CloudWatch/ECS → snapshots firmados en DynamoDB → caché de lectura de 3 s, con dashboard Cognito PKCE y clave HMAC en Secrets Manager. Se verificaron firmas, fallos de fuente, coordinación, frescura y contrato mediante tests; las validaciones AWS y de carga se reportan por versión sin atribuir a esta ampliación el benchmark anterior de fixtures.
