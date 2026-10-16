# Evidencia del bootstrap AWS

Aplicación autorizada por el usuario: 8 recursos creados, 0 modificados y 0 destruidos. Cuenta 026249143093, región us-east-1, perfil humano SSO devops-challenge.

- Bucket: infra-signal-lab-tfstate-026249143093-us-east-1. Verificado versionamiento Enabled y las cuatro protecciones de acceso público activas. Terraform configura cifrado AES256, política TLS y prevent_destroy.
- ECR: 026249143093.dkr.ecr.us-east-1.amazonaws.com/infra-signal-lab. Verificados tags IMMUTABLE y scanOnPush=true. Limpieza solo de imágenes sin etiqueta tras 7 días.
- Presupuesto: infra-signal-lab-account-monthly, USD 80 mensuales para la cuenta. Alertas ACTUAL y FORECASTED al superar el 100 % (USD 80); correo configurado en tfvars local ignorado. Créditos y reembolsos excluidos. No es un límite automático de gasto.
- Estado bootstrap migrado a S3, key infra-signal/bootstrap.tfstate, con encrypt=true y use_lockfile=true. Antes de migrar, HeadObject devolvió 404; después, confirmó objeto con AES256 y VersionId. No se imprimió el contenido del estado.

backend.tf usa backend S3 vacío y lab.tfbackend local (ignorado por Git) guarda los parámetros. Para nuevas máquinas: configurar el mismo backend con bucket/key/región/encrypt/use_lockfile mediante terraform init. No crear otro estado para los mismos recursos.

Todavía no se han creado con este paso ECS, ALB, NAT, VPC Link, API Gateway ni Cognito. No se ha publicado una imagen en ECR. Los siguientes pasos requieren build/publicación y un plan separado de infraestructura para revisión.
