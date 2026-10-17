# Correspondencia con el diagrama acordado

La arquitectura principal está desplegada. Esto no implica que cada elemento opcional del dibujo exista ni que la capacidad máxima esté demostrada.

| Elemento del diagrama | Implementación / evidencia | Diferencia o límite |
|---|---|---|
| API Gateway HTTP API público | Endpoint HTTPS y rutas verificadas | Dominio AWS execute-api |
| Cognito / JWT | Login code + PKCE y cinco consultas protegidas 200 | No federación externa; cliente público sin secreto |
| VPC Link | Integración privada desplegada | Sin acceso público directo al ALB |
| VPC y dos AZ privadas | Subredes y ALB en dos AZ; tareas observadas en ambas | CIDR implementado 10.80.0.0/16; el dibujo inicial era ilustrativo |
| ALB interno / health checks | Targets saludables; tráfico Gateway→ALB→tareas | HTTP dentro de la VPC; no TLS extremo a extremo |
| ECS Fargate stateless | API Go Linux/amd64; tareas privadas, read-only, no-root | CloudWatch/ECS → DynamoDB; evidencia real en telemetry.md |
| ECR | Imágenes por SHA inmutable, pull con execution role | Sin access keys permanentes para Actions |
| Autoscaling | Políticas CPU y requests por target | Sin política de memoria; pico de 10k probado con 16 tareas preparadas; no se probó respuesta del autoscaling al pico |
| CloudWatch | Logs Gateway/ECS; métricas y alarmas 5xx; eventos leídos | Sin notificaciones de alarmas; ALB access logs no habilitados |
| CI/CD GitHub Actions | Verify→Publish→Plan→Apply→smoke con OIDC | Inicio manual y aprobación humana; no deploy automático en cada push |
| Secrets Manager | Clave HMAC de snapshots creada e inyectada por ECS | Integración validada con snapshots; sin rotación automática |
| ACM / dominio custom | HTTPS provisto por API Gateway en dominio AWS | No hay dominio propio ni certificado ACM administrado por este Terraform |

El S3 de estado, presupuesto y NAT por AZ forman parte del código, aunque no aparecían con el mismo detalle en la imagen inicial. Los límites de rendimiento y el alcance de pruebas están en validation-results.md y capacity-plan.md. Los bonus se tratan por separado.
