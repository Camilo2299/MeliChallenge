# Despliegue inicial desde macOS

Usar Terraform >=1.10, AWS CLI v2, Docker Desktop y perfil SSO `devops-challenge`. Ejecutar desde devops-challenge/. No ejecutar apply hasta revisar el plan, cuenta, región y costo y obtener autorización. Estos comandos son el procedimiento, no evidencia de ejecución.

## 1. Sesión y parámetros

```bash
aws sso login --profile devops-challenge
export AWS_PROFILE=devops-challenge
export AWS_REGION=us-east-1
aws sts get-caller-identity
cp iac/bootstrap/terraform.tfvars.example iac/bootstrap/terraform.tfvars
```

Editar el archivo ignorado por Git con región, presupuesto aprobado y correo real. Los créditos reportados no confirman el presupuesto. No usar root. Verificar que la cuenta sea la acordada y que no haya recursos homónimos de otro proyecto. `lab` y `production` usan estados, nombres y permisos separados.

## 2. Plan bootstrap y revisión

```bash
terraform -chdir=iac/bootstrap init -input=false
terraform -chdir=iac/bootstrap fmt -check
terraform -chdir=iac/bootstrap validate
terraform -chdir=iac/bootstrap plan -input=false -out=bootstrap.tfplan
terraform -chdir=iac/bootstrap show -no-color bootstrap.tfplan
```

Bootstrap crea S3 privado/versionado/cifrado/TLS, ECR inmutable y presupuesto con alertas. Su estado inicialmente es local: no subir terraform.tfstate a Git y respaldarlo de forma segura. ECR retiene versiones etiquetadas para evitar perder la imagen de rollback.

**Solo después de autorizar el plan concreto:**

```bash
terraform -chdir=iac/bootstrap apply bootstrap.tfplan
STATE_BUCKET=$(terraform -chdir=iac/bootstrap output -raw state_bucket)
REPOSITORY=$(terraform -chdir=iac/bootstrap output -raw ecr_repository_url)
```

Migrar también el estado bootstrap a S3: agregar `terraform { backend "s3" {} }` en `iac/bootstrap/backend.tf`, ejecutar `terraform -chdir=iac/bootstrap init -migrate-state` con bucket, key `infra-signal/bootstrap.tfstate`, región, encrypt=true y use_lockfile=true; revisar y aceptar la migración interactiva. Verificar `terraform state list` y el objeto S3 antes de archivar la copia local. No ejecutar migrate-state si el backend destino ya contiene un estado ajeno.

## 3. Imagen Linux/amd64

Definir RELEASE_TAG como identificador único del código revisado (SHA de Git cuando exista). La etiqueta es inmutable: no reutilizarla para contenidos distintos.

```bash
export RELEASE_TAG=REPLACE_WITH_UNIQUE_RELEASE
REGISTRY="${REPOSITORY%%/*}"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$REPOSITORY:$RELEASE_TAG" ./api
docker push "$REPOSITORY:$RELEASE_TAG"
```

El build ejecuta tests. Publicar la imagen antes de crear el servicio ECS. Este flujo local se reemplazará por GitHub Actions con OIDC.

## 4. Plan infraestructura y revisión

```bash
cp iac/terraform.tfvars.example iac/terraform.tfvars
# Editar image_tag para coincidir exactamente con RELEASE_TAG.
terraform -chdir=iac init -input=false \
  -backend-config="bucket=$STATE_BUCKET" \
  -backend-config="key=infra-signal/lab.tfstate" \
  -backend-config="region=$AWS_REGION" \
  -backend-config="encrypt=true" -backend-config="use_lockfile=true"
terraform -chdir=iac validate
terraform -chdir=iac plan -input=false -out=infrastructure.tfplan
terraform -chdir=iac show -no-color infrastructure.tfplan
```

Comprobar cuota Fargate, EIP/NAT, ALB y API Gateway, costos, imagen disponible, SG, dos AZ y ausencia de destrucciones inesperadas. El backend requiere acceso S3 al prefijo del estado y a su `.tflock`, incluyendo DeleteObject para el lockfile; no es necesario DynamoDB.

**Solo tras autorizar el plan de infraestructura:**

```bash
terraform -chdir=iac apply infrastructure.tfplan
BASE_URL=$(terraform -chdir=iac output -raw api_url)
bash cicd/smoke.sh "$BASE_URL"
```

El smoke comprueba readiness 200 y rechazo JWT 401. Todavía falta validar una solicitud autenticada: crear un usuario administrado en Cognito, completar cambio de contraseña y OAuth authorization code + PKCE con callback permitida, solicitar scope `infra-metrics/read`, y probar el access token. No guardar tokens o contraseñas en Terraform ni en Git. No se han implementado aún las pruebas OAuth de extremo a extremo.

## GitHub después del primer despliegue

Preparar OIDC y roles separados de Terraform/aplicación cuando se conozca el repositorio. El workflow existente es una plantilla: requiere variables AWS_REGION, TF_ENVIRONMENT, TF_STATE_BUCKET, ECR_REPOSITORY_URL, AWS_PLAN_ROLE_ARN y AWS_DEPLOY_ROLE_ARN, y entornos production-plan y production. Proteger production con revisores. No usar access keys permanentes. El rol de plan del workflow actual también publica la imagen; separar esas capacidades al cerrar IAM. No afirmar CI/CD operativo hasta ejecutar y verificar un workflow real.
