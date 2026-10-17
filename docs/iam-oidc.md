# GitHub Actions y AWS: identidades y permisos

La operación actual se describe en [lifecycle.md](lifecycle.md). El entorno AWS es `lab`, `us-east-1`, cuenta `026249143093`; los nombres GitHub `production` y `production-plan` no representan un segundo entorno AWS.

| Rol | Environment GitHub | Alcance |
|---|---|---|
| `meli-ci-lab-publish` | `image-publish` | Autenticación y publicación ECR del repositorio del laboratorio. |
| `meli-ci-lab-plan` | `production-plan` | Lecturas y lockfile; retenido para comprobaciones OIDC y planificación separada. No es un job obligatorio del flujo nuevo. |
| `meli-ci-lab-terraform` | `production` | Plan/apply/destroy de la aplicación y smoke autenticado. No mantiene sus propios roles CI. |
| `meli-ci-lab-foundation` | `foundation` | Mantenimiento de bootstrap y roles/políticas CI desde Actions. Sin borrados/reemplazos de la base. |

Todos los trusts exigen `aud=sts.amazonaws.com` y el subject exacto `repo:Camilo2299@80074245/MeliChallenge@1421554656:environment:NOMBRE`. El repositorio usa IDs inmutables en sus subjects OIDC. Los environments permiten `main`; `production` y `foundation` tienen revisión del único responsable. No es revisión independiente de dos personas. No se almacenan access keys permanentes en Actions.

## Separación de confianza

`iac/bootstrap` contiene el bucket S3 privado, versionado/cifrado, ECR con etiquetas inmutables y presupuesto. `iac/identity` contiene OIDC y los tres roles CI iniciales. `iac/control` contiene el rol foundation y el techo de permisos CI. Los estados separados viven bajo `infra-signal/` en `infra-signal-lab-tfstate-026249143093-us-east-1`. La aplicación usa `lab.tfstate`; el generador de capacidad tiene su propio estado y no forma parte del destroy habitual.

El rol de aplicación solo escribe su estado/lockfile y `lifecycle.json`. El rol foundation escribe los estados bootstrap/identity y sus lockfiles. Ninguno administra el estado `control.tfstate`. La creación inicial de esta confianza requiere SSO externo; no puede ser creada por un pipeline que aún no está autorizado.

Los roles CI tienen el límite `meli-ci-lab-ci-ceiling`: sus políticas efectivas siguen siendo más restrictivas. El techo admite familias de servicios regionales necesarias, S3 de aplicación y operaciones IAM exclusivamente sobre los roles runtime, con `PassRole` condicionado a ECS. No concede administración IAM de la cuenta. Crear roles runtime exige el límite `meli-ci-lab-runtime-boundary`, que permite únicamente leer la imagen/secreto, emitir logs y consultar/escribir la telemetría prevista. Así, un cambio en las políticas inline runtime no permite concederles acceso administrativo.

Foundation puede mantener las políticas con prefijos `meli-ci-lab-publish-*`, `plan-*` y `terraform-*`, y adjuntarlas únicamente a esos tres roles CI. Exige su techo de permisos al crear/cambiar el boundary. No puede modificar su propio rol/política, el techo CI ni el techo runtime. Estos elementos de confianza requieren la identidad externa para cambiarse. El guard de mantenimiento rechaza borrados/reemplazos y cambios del techo runtime antes del apply.

## Operación y validación

**Verify Plan and Deploy** realiza gates de calidad, publicación ECR, y plan/apply con el rol de aplicación, seguido de prueba autenticada. El despliegue automático se controla con `LAB_AUTODEPLOY_ENABLED`. **Lab lifecycle** permite deploy/rollback/plan/destroy-plan/destroy. **Foundation maintenance** usa el rol separado para bootstrap/identity. Los workflows comparten exclusión mutua para evitar mutaciones simultáneas.

`cicd/check_iam.py` comprueba tamaño de políticas, ausencia de acciones wildcard en los documentos efectivos, publisher restringido a ECR, rol plan sin mutaciones de infraestructura y `PassRole` acotado. Los techos tienen alcance más amplio que los permisos efectivos y se prueban por separado. Terraform prueba trusts exactos y los scripts prueban los guards de destrucción/mantenimiento. AWS Access Analyzer valida estructura/acciones; no demuestra por sí solo permisos suficientes ni aislamiento completo.

Las políticas iniciales y de destrucción se derivaron con IAM Policy Autopilot desde planes Terraform reales, y se depuraron para eliminar permisos auxiliares/recursos ajenos y limitar ARNs. Ejemplo reproducible, sin publicar automáticamente las políticas:

```bash
umask 077
terraform -chdir=iac show -json /ruta/plan.tfplan > /tmp/permissions-plan.json
uvx iam-policy-autopilot@latest generate-policies /tmp/permissions-plan.json \
  --region us-east-1 --account 026249143093 --resource-cutoff 100 --pretty
```

Tratar plan/JSON como sensibles; no subirlos a Git. Para acciones de mantenimiento consultar la [referencia oficial de autorización](https://docs.aws.amazon.com/service-authorization/latest/reference/reference_policies_actions-resources-contextkeys.html). Una política generada no sustituye revisión del alcance ni la prueba real.

Se requieren wildcards de IDs para crear/recrear recursos. Las mutaciones de red existente exigen `Project=infra-signal`; algunos permisos de API Gateway/Cognito son regionales y no garantizan aislamiento perfecto por proyecto. No se ha instalado una auditoría dedicada de CloudTrail/alertas para cambios IAM. Un plan de destrucción exitoso no prueba cada permiso de borrado: el ciclo destructivo real sigue sin ejecutarse durante esta instalación.

## Configuración GitHub para reproducir los workflows

En **Settings → Secrets and variables → Actions**, configurar las siguientes variables con valores de los outputs Terraform de la cuenta destino. También pueden existir en el environment correspondiente; comprobar su alcance antes de ejecutar.

| Variable | Uso / valor del laboratorio |
|---|---|
| `AWS_REGION` | `us-east-1` |
| `AWS_ACCOUNT_ID` | ID de cuenta destino; laboratorio `026249143093` |
| `TF_ENVIRONMENT` | `lab` |
| `TF_STATE_BUCKET` | Bucket de bootstrap; laboratorio `infra-signal-lab-tfstate-026249143093-us-east-1` |
| `ECR_REPOSITORY_URL` | URL del repositorio ECR creado por bootstrap |
| `AWS_PUBLISH_ROLE_ARN` | ARN del rol publisher de identidad |
| `AWS_DEPLOY_ROLE_ARN` | ARN del rol Terraform de identidad |
| `AWS_FOUNDATION_ROLE_ARN` | ARN del rol foundation de control |
| `LAB_AUTODEPLOY_ENABLED` | `true` habilita despliegue desde push main |
| `DEMO_USER_EMAIL` | Correo elegido para el usuario de nuevas generaciones; no envía invitación |
| `MONTHLY_BUDGET_USD` | `80`; alerta presupuestaria, no límite automático de gasto |

Crear el **secret** `BUDGET_ALERT_EMAIL` para foundation; no es una access key ni una contraseña AWS. Nunca guardar contraseñas, JWT o access keys como variables públicas. Los environments `image-publish`, `production`, `production-plan` (rol retenido) y `foundation` deben coincidir con los subjects de sus trusts; limitar ramas a main y configurar los gates de revisión previstos. En otra cuenta/repositorio, adaptar los IDs inmutables OIDC y políticas; copiar solo estas variables no instala la raíz de confianza.
