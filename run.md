# Ejecutar y demostrar la solución

## Local

Desde la raíz del repositorio:

```bash
docker compose up --build
```

En otra terminal:

```bash
curl -i http://localhost:8080/health/ready
curl -s http://localhost:8080/v1/services
curl -s http://localhost:8080/v1/services/gateway
curl -s http://localhost:8080/v1/summary
```

La documentación está en http://localhost:8080/docs. Las consultas locales no requieren autenticación; no exponer directamente este puerto a Internet. Los datos son sintéticos.

## Laboratorio AWS desplegado

Las URLs e IDs siguientes corresponden al despliegue documentado. Tras destruir/recrear, obtener los nuevos valores de los outputs del workflow/Terraform; los anteriores dejan de ser válidos.

```bash
bash cicd/smoke.sh https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com
```

Este smoke comprueba readiness 200 y negocio sin token 401. Para verificar autorización real con el usuario de demostración previamente creado:

```bash
python3 cicd/login_and_test.py \
  --api-url https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com \
  --authorize-url https://infra-signal-lab-026249143093.auth.us-east-1.amazoncognito.com/oauth2/authorize \
  --client-id 3rgsnh8b52lcqnlm00vnltlpdr
```

Requiere Python 3, navegador y puerto local 8085 libre. El usuario ingresa su contraseña en Cognito; el script usa code + PKCE, conserva tokens en memoria y comprueba siete consultas protegidas. El reporte /tmp/meli-authenticated-smoke.json no contiene tokens. No compartir contraseñas ni copiar JWT al README. Las credenciales no forman parte de la entrega; para acceso de evaluadores, acordar previamente un usuario administrativo de demostración.

## Vista de métricas reales

Abrir https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com/dashboard y elegir **Iniciar sesión**. La página usa Cognito y mantiene el access token solo en memoria. Se actualiza cada 3 s; las muestras de CloudWatch tienen periodo de 60 s y fecha propia. El servicio AWS es `infra-signal-lab` en entorno `lab`; `gateway` pertenece únicamente al modo local de ejemplo.

Ver [telemetría](docs/telemetry.md) para rutas, persistencia, frescura y límites. El smoke automatizado `cicd/telemetry_smoke.py` modifica temporalmente la audiencia JWT para un cliente M2M de prueba y lo retira al terminar; requiere autorización para esas operaciones. No es necesario para el uso normal del dashboard.

## Reproducir el despliegue

1. Seguir [bootstrap](cicd/bootstrap.md) para estado, ECR y presupuesto; revisar [IAM/OIDC](docs/iam-oidc.md) y adaptar cuenta, repo y políticas antes de usar otra cuenta.
2. Configurar las variables y entornos protegidos de GitHub descritos allí. No crear access keys permanentes para Actions.
3. En el laboratorio existente, usar **Actions → Lab lifecycle → deploy** en main. También se despliega desde push main cuando `LAB_AUTODEPLOY_ENABLED=true`, después de CI y del gate protegido `production`. Los PR ejecutan verificaciones.
4. Revisar costos y alcance antes de aprobar el job del environment `production`. El controlador genera y aplica el mismo plan guardado dentro del job; no publica un artefacto `terraform-plan` ni ofrece una aprobación adicional entre plan y apply. Para inspeccionar un plan previamente, usar **Lab lifecycle → plan**; el deploy posterior genera un plan nuevo. El workflow espera estabilidad ECS y comprueba autenticación, persistencia y dos recolecciones reales.
5. Ejecutar el login anterior para la validación humana. El artefacto `deployment-verification` contiene el reporte sin tokens. Para mantenimiento de bootstrap/identidad usar **Foundation maintenance**. Ver [lifecycle](docs/lifecycle.md).

Tras un apply parcial, generar otro plan sobre el estado remoto: no reutilizar el binario anterior. No modificar el estado para ocultar errores.

## Operación y retiro

Ver [runbook](docs/runbook.md) para diagnóstico, rollback y desmontaje autorizado. NAT, ALB y tareas generan costos mientras existan. El presupuesto alerta a USD 80; no detiene los recursos. No ejecutar el guion k6 de 10k RPS sin dimensionamiento y autorización.
