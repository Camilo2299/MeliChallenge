# Ciclo del laboratorio por GitHub Actions

El workflow **Lab lifecycle** centraliza la plataforma `infra-signal-lab`, región `us-east-1`, cuenta `026249143093`. Ejecución únicamente desde `main`, mediante OIDC y el environment protegido `production`. No usa access keys de larga duración. Los workflows que escriben el estado comparten `infra-signal-deployment` y no se cancelan entre sí.

| Operación | Resultado |
|---|---|
| `plan` | Revisa la configuración conservando la imagen y generación actuales; no aplica cambios. |
| `deploy` | Publica imagen SHA inmutable, aplica un plan guardado, espera ECS y verifica API, Cognito y telemetría persistida. Con estado vacío reconstruye la plataforma. |
| `rollback` | Aplica con Terraform la imagen del despliegue anterior exitoso registrada en S3; vuelve a verificar la aplicación. |
| `destroy-plan` | Muestra los recursos que se borrarían, sin desactivar protecciones ni aplicar. |
| `destroy` | Exige `DESTROY infra-signal-lab DATA`. Desactiva protecciones de ALB/DynamoDB mediante un plan dirigido y aplica un nuevo plan de destrucción. Borra métricas y usuarios del laboratorio. |

Ejecutar desde **Actions → Lab lifecycle → Run workflow → main**. No modificar directamente ECS, Cognito o el estado para estas operaciones. Reintentar `destroy` completa una destrucción interrumpida. El estado `destroying` bloquea despliegues hasta terminar esa operación.

## Qué permanece

Se retienen el bootstrap (S3 versionado/cifrado, ECR con releases, presupuesto) y la identidad (OIDC, roles CI y límite de permisos runtime). Sus estados son distintos del estado de la aplicación. Esta base es necesaria para que Actions pueda autenticarse y reconstruir el laboratorio. `destroy` no equivale a vaciar la cuenta AWS y no elimina esa base. Imágenes, versiones de estado y secretos pendientes de eliminación pueden seguir generando cargos.

Crear inicialmente el bucket y la confianza OIDC requiere una identidad AWS externa al pipeline que todavía no existe. La actualización inicial de permisos de esta migración se realiza con SSO y Terraform en `iac/identity`, y queda registrada en ese estado. **El mantenimiento de bootstrap/identidad no está automatizado por estos workflows**: no se otorgan al rol de la aplicación permisos para reescribir su propio acceso. Una reconstrucción de la aplicación no necesita repetir el bootstrap. Para eliminar también la base o instalar en otra cuenta se necesita nuevamente una identidad administrativa y configurar variables/trust del repositorio.

## Reconstrucción y datos

`infra-signal/lifecycle.json`, en el bucket de estado privado, conserva intención (`present`, `destroying`, `absent`), generación, release y release anterior. No contiene contraseñas. Las nuevas generaciones añaden el ID de ejecución al dominio Cognito y a los nombres de secretos, evitando colisiones con secretos pendientes de eliminación durante siete días. Un reintento reutiliza la generación de la creación parcial.

Las URLs/IDs se obtienen de outputs de Terraform; cambian tras reconstruir. La nueva tabla comienza vacía y el recolector escribe datos reales de la infraestructura nueva. No se restaura el historial anterior. Para generaciones nuevas se crea el usuario indicado por `DEMO_USER_EMAIL`, sin invitación por correo; sus credenciales iniciales se guardan en el secreto `demo-login-r…`, fuera del estado y de los artefactos públicos. Cambiar la contraseña en el primer ingreso. Los usuarios existentes no se modifican.

El smoke crea un cliente M2M temporal, prueba siete consultas autenticadas y dos recolecciones sucesivas, comprueba DynamoDB y referencia a Secrets Manager. Restaura la audiencia y elimina el cliente en `finally`; un paso `always()` vuelve a intentar la limpieza si el proceso fue interrumpido. Una pérdida completa del runner requiere reconciliar el cliente/audiencia con la siguiente ejecución; no se garantiza cleanup ante la desaparición del runner.

## Push y límites

`LAB_AUTODEPLOY_ENABLED=true` habilita despliegue después de los gates de calidad en push a `main`. El environment `production` conserva sus reglas de aprobación existentes. Un push con intención `absent` o `destroying` no recrea la aplicación; puede publicar una imagen pero omite el apply. La recreación exige `deploy` explícito. Las operaciones manuales de deploy también pasan los mismos gates.

Las pruebas masivas históricas y simulacros no se ejecutan automáticamente con este cambio. Este workflow no certifica destrucción/recreación hasta ejecutar y registrar ambas operaciones. Un plan exitoso no demuestra permisos suficientes para cada llamada de borrado ni tiempos de liberación de AWS. No se ejecuta destrucción real durante la instalación del workflow. No se garantiza cero downtime al aplicar o reconstruir. Si falla un despliegue, ECS conserva su circuit breaker; `rollback` recupera la imagen previa cuando existe un despliegue exitoso registrado.
