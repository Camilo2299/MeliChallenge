# Uso responsable de IA en esta entrega

Se utilizó asistencia de IA para estructurar una propuesta de arquitectura, generar un esqueleto de API Go (`net/http`), pruebas iniciales, Docker, Terraform, CI/CD y documentación. Las decisiones técnicas, validación local, revisión de IAM, revisión de costos cloud, pruebas de carga y verificación del despliegue son responsabilidad del candidato.

## Verificaciones necesarias antes de presentar
- Ejecutar los tests y validar el comportamiento HTTP.
- Ejecutar `terraform fmt`, `terraform init` y `terraform validate` contra la versión correcta del provider.
- Revisar el `terraform plan` completo (incluidos costos, permisos y cambios destructivos).
- Confirmar que la imagen arranca en ECS y que el ALB informa targets healthy.
- Ejecutar k6 con tráfico gradual antes de afirmar 10k RPS sostenidos.

No se presentan como hechas pruebas o despliegues que no se hayan ejecutado. La API entrega información ilustrativa, no datos de infraestructura reales.
