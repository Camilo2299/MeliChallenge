# Ciclo del laboratorio por GitHub Actions

**Cierre del 23 de octubre de 2026 (Bogotá):** [destroy exitoso](https://github.com/Camilo2299/MeliChallenge/actions/runs/40053480336), estado de aplicación vacío y manifiesto ausente. El intento anterior retiró la plataforma pero falló al disociar las dos IP de NAT; [foundation](https://github.com/Camilo2299/MeliChallenge/actions/runs/40053255793) corrigió el permiso y el reintento liberó ambas. No se ejecutó reconstrucción. Las referencias posteriores a destrucción no ensayada describen el estado previo a este cierre; sigue pendiente validar el ciclo completo con reconstrucción.

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

Se retienen el bootstrap (S3 versionado/cifrado, ECR con releases, presupuesto) y la identidad (OIDC, roles CI y límite de permisos runtime). Sus estados son distintos del estado de la aplicación. Esta base es necesaria para que Actions pueda autenticarse y reconstruir el laboratorio. `destroy` no equivale a vaciar la cuenta AWS y no elimina esa base. Las imágenes y versiones de estado retenidas pueden generar cargos; los secretos quedan pendientes de eliminación durante siete días.

Crear inicialmente el bucket y la confianza OIDC requiere una identidad AWS externa al pipeline que todavía no existe. La instalación inicial de esta migración usa SSO y Terraform y se registra en estados separados. Después, **Foundation maintenance** mantiene `iac/bootstrap` (estado, ECR y presupuesto) e `iac/identity` (roles/políticas CI) desde Actions, con un rol y environment `foundation` separados, protegidos y limitados a `main`. Elegir stack `bootstrap` o `identity` y operación `plan` o `apply`. Rechaza borrados y reemplazos; nunca se usa para destruir la base.

La raíz de confianza `iac/control` (rol de mantenimiento y techo de permisos CI), y el techo runtime de identidad, requieren la identidad externa para modificarse. El rol foundation no puede modificarse a sí mismo ni modificar estos techos. Los roles CI tienen un techo de permisos separado de sus políticas: no pueden obtener administración IAM aunque se cambien sus documentos. El techo permite las familias de servicios del laboratorio en la región; los permisos efectivos siguen limitados por las políticas CI más específicas. Este rol de mantenimiento es privilegiado y debe revisarse como un cambio de plataforma.

Una reconstrucción de la aplicación no necesita repetir el bootstrap. Vaciar también la base de confianza, o instalar en otra cuenta, requiere nuevamente una identidad administrativa y configurar variables/trust. Esto no se presenta como una cuenta que se puede borrar íntegramente y luego recuperar sin ninguna identidad externa.

## Reconstrucción y datos

`infra-signal/lifecycle.json`, en el bucket de estado privado, conserva intención (`present`, `destroying`, `absent`), generación, release y release anterior. No contiene contraseñas. Las nuevas generaciones añaden el ID de ejecución al dominio Cognito y a los nombres de secretos, evitando colisiones con secretos pendientes de eliminación durante siete días. Un reintento reutiliza la generación de la creación parcial.

Las URLs/IDs se obtienen de outputs de Terraform; cambian tras reconstruir. La nueva tabla comienza vacía y el recolector escribe datos reales de la infraestructura nueva. No se restaura el historial anterior. Para generaciones nuevas se crea el usuario indicado por `DEMO_USER_EMAIL`, sin invitación por correo; sus credenciales iniciales se guardan en el secreto `demo-login-r…`, fuera del estado y de los artefactos públicos. Cambiar la contraseña en el primer ingreso. Los usuarios existentes no se modifican.

El smoke crea un cliente M2M temporal, prueba siete consultas autenticadas y dos recolecciones sucesivas, comprueba DynamoDB y referencia a Secrets Manager. Restaura la audiencia y elimina el cliente en `finally`; un paso `always()` vuelve a intentar la limpieza si el proceso fue interrumpido. Una pérdida completa del runner requiere reconciliar el cliente/audiencia con la siguiente ejecución; no se garantiza cleanup ante la desaparición del runner.

## Push y límites

`LAB_AUTODEPLOY_ENABLED=true` habilita despliegue después de los gates de calidad en push a `main`. El environment `production` conserva sus reglas de aprobación existentes. Un push con intención `absent` o `destroying` no recrea la aplicación; puede publicar una imagen pero omite el apply. La recreación exige `deploy` explícito. Las operaciones manuales de deploy también pasan los mismos gates.

Las pruebas masivas históricas y simulacros no se ejecutan automáticamente con este cambio. Estos workflows no certifican destrucción/recreación hasta ejecutar y registrar ambas operaciones. Un plan exitoso no demuestra permisos suficientes para cada llamada de borrado ni tiempos de liberación de AWS. No se ejecuta destrucción real durante la instalación del workflow. No se garantiza cero downtime al aplicar o reconstruir. Si falla un despliegue, ECS conserva su circuit breaker; `rollback` recupera la imagen previa cuando existe un despliegue exitoso registrado.
