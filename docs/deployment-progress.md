# Historial del despliegue y validación

**Estado de referencia actual:** telemetría CloudWatch/ECS persistida en DynamoDB y firmada con Secrets Manager. Versión real: 5k/60 s y 10k/30 s; el intento real de 10k/60 s tuvo descartes. [Resultados](telemetry-capacity-results.md). [Deploy posterior por Actions](https://github.com/Camilo2299/MeliChallenge/actions/runs/39001245527) con smoke autenticado y [foundation](https://github.com/Camilo2299/MeliChallenge/actions/runs/39000421161) exitosos. Destroy/recreate completo aún no ensayado.

Las secciones siguientes conservan el estado de cada hito histórico; referencias a pendientes, revisión :6 o pico de fixtures no representan el estado actual. Ver [resumen vigente](morning-report.md).

Ejecución: https://github.com/Camilo2299/MeliChallenge/actions/runs/38846419254

- Verify pasó: Go, Docker Linux/amd64, Trivy y validaciones/pruebas Terraform.
- Publish pasó: imagen ECR inmutable 9d003ec272018bc6e3a8262e833ed6c37cf11ac5.
- Plan pasó tras corregir la lectura ecr:DescribeImages. Resultado: **55 recursos nuevos, 0 modificaciones y 0 eliminaciones**.
- El primer apply fue aprobado, creó 35 recursos y falló por permisos IAM de API Gateway, reglas de security groups y lectura de atributos EC2 para ALB. El estado remoto conserva lo creado.
- Se corrigieron tres políticas IAM mediante Terraform (0 altas, 3 cambios, 0 bajas): lectura ec2:DescribeAccountAttributes; autorización de reglas nuevas con RequestTag de proyecto/entorno; API Gateway acotado por ARN regional sin la condición RequestedRegion adicional. El ajuste de API Gateway requiere confirmación en el siguiente apply.
- Plan local de recuperación con la imagen original: **20 altas, 0 cambios, 0 bajas**. No reutilizar el plan binario del apply fallido: generar un plan nuevo. El siguiente workflow publicará su propio SHA y puede reemplazar la definición de tarea anterior. El despliegue y las pruebas reales siguen pendientes.
- Cuota Fargate On-Demand consultada: 6 vCPU. Laboratorio: 2 tareas de 0,5 vCPU/1 GiB, máximo 4. No demuestra 10k RPS.

Costo base estimado: USD 4,12 por 24 horas, más LCUs, tráfico, API Gateway, Cognito, observabilidad y almacenamiento. Alerta USD 80; no detiene recursos. Ver docs/costs.md.

## Validación posterior

1. Verificar tareas y targets saludables en dos AZ, imagen exacta y respuesta HTTPS.
2. Ejecutar cicd/smoke.sh contra api_url: readiness 200 y negocio sin token 401.
3. Crear usuario de demostración usando la sesión humana SSO:

```bash
python3 cicd/create_demo_user.py --pool-id POOL_ID --username TU_CORREO
```

El usuario es un dato operacional de Cognito, separado de Terraform. No se envía invitación ni se marca el email como verificado. La contraseña temporal se guarda en un archivo local privado; no se imprime ni se versiona. Cambiarla en el primer login y retirar ese archivo.

4. Login con PKCE y pruebas autenticadas:

```bash
python3 cicd/login_and_test.py --api-url HTTPS_API_URL \
  --authorize-url HTTPS_COGNITO_AUTHORIZE_URL --client-id CLIENT_ID
```

Callback: http://localhost:8085/callback. Se valida state y se intercambia el código con PKCE. Solo se solicita infra-metrics/read; no se usan claims de ID token. El access token permanece en memoria; API Gateway valida su JWT y scope. El reporte /tmp/meli-authenticated-smoke.json no contiene tokens.

Estos pasos autenticados y el despliegue todavía están pendientes. No se ejecutaron pruebas de 10.000 RPS.

## Segundo apply y recuperación

La ejecución 38851275718 completó reglas de seguridad, ALB interno, listener y alarmas del ALB. Falló en tres operaciones: retirada de la definición de tarea anterior, creación del VPC Link y creación del stage con etiquetas.

- `ecs:DeregisterTaskDefinition` no admite restricción por ARN de tarea en IAM. Se usa `Resource: "*"` exclusivamente para esa acción, conservando la condición regional. Referencia: https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecs.html.
- El cambio anterior de `RequestedRegion` no resolvió el etiquetado al crear recursos API Gateway. Se añade experimentalmente el permiso exacto `apigateway:TagResource` exigido por ambos errores, limitado a los ARN de VPC Links regionales y stages de la API `v1dbllhj9a`. El catálogo público y Access Analyzer no reconocen esa acción; su aceptación por IAM no acredita su eficacia. Debe comprobarse en el siguiente apply y revisarse como excepción, no como patrón reutilizable. Se mantienen los verbos HTTP documentados para las demás operaciones.
- Nunca reintentar el plan binario antiguo tras un apply parcial. Generar nuevamente el plan sobre el estado remoto y revisar los cambios antes de aplicar.

## Tercer apply: stage y entrega de logs

La ejecución 38852785837 creó servicio ECS, autoscaling, VPC Link, integración y rutas. Esto confirma que funcionaron los cambios de deregistro ECS y etiquetado al crear el VPC Link. El stage falló únicamente al activar sus logs por falta de `logs:CreateLogDelivery`.

Se incorporan los siete permisos de gestión de entrega y políticas de logs documentados para HTTP API (Create/Get/Update/DeleteLogDelivery, ListLogDeliveries, PutResourcePolicy y DescribeResourcePolicies). CreateLogGroup y DescribeLogGroups ya estaban concedidos. La nueva declaración usa `Resource: "*"`, como requiere este mecanismo, y limita RequestedRegion a us-east-1. Permite administrar la entrega y las políticas de logs regionales; no se debe describir como acotada a un único log group. Referencia: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html.

Plan de identidad: 0 altas, 1 cambio, 0 bajas. Falta confirmar la creación del stage y ejecutar la verificación HTTPS.

## Despliegue completado

Evidencia: https://github.com/Camilo2299/MeliChallenge/actions/runs/38857181854

- Verify, Publish, Plan y Apply finalizaron con success.
- La verificación posterior del pipeline pasó. Se repitió localmente `cicd/smoke.sh`: readiness 200 y rechazo JWT sin token 401.
- API pública: https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com
- Se creó el usuario de demostración autorizado en Cognito sin invitación automática; la contraseña temporal queda solo en un archivo local privado, fuera del repositorio.
- Login Cognito completado por el usuario y cinco consultas autenticadas verificadas con HTTP 200. Evidencia sin tokens: [authenticated-smoke.json](evidence/authenticated-smoke.json). Se comprobó inventario, filtro production, detalle gateway, despliegues y resumen.
- Se corrigió el helper OAuth: Cognito no devuelve un campo scope en el nivel superior de la respuesta del token endpoint; API Gateway valida JWT y scope al atender cada consulta protegida.
- Los datos son fixtures de demostración. No se ejecutaron pruebas de carga de 10.000 RPS ni pruebas de failover/rollback.

## Cierre de validación operacional

Se ejecutaron carga local 100 RPS/60 s y AWS autenticada 30 RPS/60 s, ambas sin errores y con p95 bajo 200 ms. Se recuperó una tarea en 58,88 s y se ensayó retorno a la revisión original con imagen idéntica. Se corrigió un fallo del helper y se conservan ambos reportes. El plan Terraform posterior con la imagen 6cc31df8eadeeb888122a90e5503350f8478688f terminó con No changes; el primer intento de lectura falló por DNS y el reintento con menor paralelismo pasó. No se aplicaron cambios Terraform adicionales ni se modificó la configuración de escala del laboratorio.

Ver [resultados y límites](validation-results.md), [alcance enterprise pendiente](production-readiness.md) y [resumen técnico](delivery-summary.md). Siguen sin probarse 10k RPS, fallo de AZ y circuit breaker ante regresiones.

## Intento de capacidad mayor

Se ejecutaron dos secuencias autorizadas de k6, con un máximo escalón completo de 2.500 RPS por un minuto. La repetición se cortó en 5k por 59 dropped_iterations, sin errores HTTP; no se ejecutó 10k. Se restauró el perfil habitual mediante Terraform y el plan final confirmó No changes. Ver capacity-results.md para métricas, limitaciones y reportes de todos los intentos. Los bonus no se ampliaron.

## Cierre regional de 10k RPS

El usuario autorizó continuar las pruebas sin aprobaciones manuales adicionales dentro del presupuesto incremental de USD 5. Un generador EC2 Linux temporal en us-east-1 y un cliente Cognito M2M completaron todos los escalones hasta 10.000 RPS. Se validaron 600.002 respuestas en la meseta de 60 s, sin errores/descartes, p95 9,05 ms y p99 21,87 ms. Terraform retiró los 14 recursos auxiliares, restauró la audiencia original y el perfil 2–4 tareas/throttle 100; el plan posterior no mostró cambios. Se ajustó operacionalmente desired_count a 2 para completar el retorno de costos, ya que ese atributo lo administra autoscaling y Terraform lo ignora. Ver capacity-results.md y evidence/regional-capacity/.
