# Referencia del arranque inicial con identidad externa

**Operación actual:** usar los workflows **Lab lifecycle** y **Foundation maintenance**, descritos en [docs/lifecycle.md](../docs/lifecycle.md). Los comandos siguientes documentan el arranque histórico o recuperación externa; no son el procedimiento normal del laboratorio existente. La confianza inicial de `iac/control` requiere SSO; no se repite al reconstruir la aplicación.

Usar Terraform >=1.11 (CI fija 1.16.5), AWS CLI v2, Docker Desktop y perfil SSO `devops-challenge`. Ejecutar desde devops-challenge/. No ejecutar apply hasta revisar el plan, cuenta, región y costo y obtener autorización. Estos comandos describen el procedimiento, no sustituyen evidencia. El laboratorio actual ya fue desplegado: consultar docs/deployment-progress.md. No repetir un bootstrap inicial ni migrar nuevamente su estado; usar el backend remoto existente.

## 1. Sesión y parámetros

```bash
aws sso login --profile devops-challenge
export AWS_PROFILE=devops-challenge
export AWS_REGION=us-east-1
aws sts get-caller-identity
cp iac/bootstrap/terraform.tfvars.example iac/bootstrap/terraform.tfvars
```

Editar el archivo ignorado por Git con región, presupuesto aprobado y correo real. Los créditos reportados no confirman el presupuesto. No usar root. Verificar que la cuenta sea la acordada y que no haya recursos homónimos de otro proyecto. Solo `lab` está desplegado. El environment GitHub `production` es un gate, no otro entorno AWS. Un entorno AWS adicional requiere estados, nombres y permisos separados.

## 2. Plan bootstrap y revisión

```bash
# Laboratorio existente: inicializar contra su estado remoto, no un estado nuevo.
terraform -chdir=iac/bootstrap init -input=false \
  -backend-config="bucket=infra-signal-lab-tfstate-026249143093-us-east-1" \
  -backend-config="key=infra-signal/bootstrap.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="encrypt=true" -backend-config="use_lockfile=true"
terraform -chdir=iac/bootstrap fmt -check
terraform -chdir=iac/bootstrap validate
terraform -chdir=iac/bootstrap plan -input=false -out=bootstrap.tfplan
terraform -chdir=iac/bootstrap show -no-color bootstrap.tfplan
```

Bootstrap crea S3 privado/versionado/cifrado/TLS, ECR inmutable y presupuesto con alertas. En el laboratorio actual su estado está en S3. Un bootstrap en una cuenta nueva necesita un arranque previo del bucket y migración controlada desde estado local; no subir terraform.tfstate a Git y respaldarlo de forma segura. ECR retiene versiones etiquetadas para evitar perder la imagen de rollback.

**Solo después de autorizar el plan concreto:**

```bash
terraform -chdir=iac/bootstrap apply bootstrap.tfplan
STATE_BUCKET=$(terraform -chdir=iac/bootstrap output -raw state_bucket)
REPOSITORY=$(terraform -chdir=iac/bootstrap output -raw ecr_repository_url)
```

Solo para una cuenta nueva cuyo bootstrap se creó primero con estado local: `iac/bootstrap/backend.tf` ya contiene el bloque S3. Para ese arranque inicial se debe preparar deliberadamente el backend local y luego restaurar el bloque S3; no aplicar este procedimiento al laboratorio existente. Para migrar aquel estado local, ejecutar `terraform -chdir=iac/bootstrap init -migrate-state` con bucket, key `infra-signal/bootstrap.tfstate`, región, encrypt=true y use_lockfile=true; revisar y aceptar la migración interactiva. Verificar `terraform state list` y el objeto S3 antes de archivar la copia local. No ejecutar migrate-state si el backend destino ya contiene un estado ajeno.

## 3. Imagen Linux/amd64

Definir RELEASE_TAG como identificador único del código revisado (SHA de Git cuando exista). La etiqueta es inmutable: no reutilizarla para contenidos distintos.

```bash
export RELEASE_TAG=REPLACE_WITH_UNIQUE_RELEASE
REGISTRY="${REPOSITORY%%/*}"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$REPOSITORY:$RELEASE_TAG" ./api
docker push "$REPOSITORY:$RELEASE_TAG"
```

El build ejecuta tests. Publicar la imagen antes de crear el servicio ECS. En la operación actual la publicación y el despliegue se realizan por GitHub Actions con OIDC.

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

El smoke básico comprueba readiness 200 y rechazo JWT 401. El pipeline actual añade `cicd/telemetry_smoke.py` con siete consultas autenticadas, persistencia y dos recolecciones reales; los tokens permanecen en memoria. Para acceso humano usar el dashboard Cognito/PKCE. En una reconstrucción nueva el workflow provisiona el usuario de demostración y guarda su contraseña inicial en Secrets Manager; no la exporta al estado o artefactos.

## Operación GitHub vigente

Consultar [identidades OIDC](../docs/iam-oidc.md) y [ciclo completo](../docs/lifecycle.md). Los roles, environments y variables ya están configurados para esta cuenta/repositorio. Mantener bootstrap/identidad con **Foundation maintenance**; publicar, desplegar, revertir o destruir la aplicación con los workflows de aplicación. `iac/control` es la raíz de confianza retenida y se mantiene con la identidad externa. No ejecutar nuevamente migraciones de estado ni bootstrap local sobre el laboratorio existente.
