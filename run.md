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

Requiere Python 3, navegador y puerto local 8085 libre. El usuario ingresa su contraseña en Cognito; el script usa code + PKCE, conserva tokens en memoria y comprueba cinco consultas protegidas. El reporte /tmp/meli-authenticated-smoke.json no contiene tokens. No compartir contraseñas ni copiar JWT al README. Las credenciales no forman parte de la entrega; para acceso de evaluadores, acordar previamente un usuario administrativo de demostración.

## Reproducir el despliegue

1. Seguir [bootstrap](cicd/bootstrap.md) para estado, ECR y presupuesto; revisar [IAM/OIDC](docs/iam-oidc.md) y adaptar cuenta, repo y políticas antes de usar otra cuenta.
2. Configurar las variables y entornos protegidos de GitHub descritos allí. No crear access keys permanentes para Actions.
3. Ejecutar Actions → workflow de despliegue → Run workflow en main, con deploy=true. Push y PR ejecutan CI; el despliegue requiere ejecución manual.
4. Revisar el artefacto terraform-plan, costos y alcance. Aprobar production para aplicar el plan guardado. El workflow espera estabilidad ECS y ejecuta el smoke HTTPS.
5. Ejecutar el login anterior para la validación autenticada. Conservar evidencias sin secretos.

Tras un apply parcial, generar otro plan sobre el estado remoto: no reutilizar el binario anterior. No modificar el estado para ocultar errores.

## Operación y retiro

Ver [runbook](docs/runbook.md) para diagnóstico, rollback y desmontaje autorizado. NAT, ALB y tareas generan costos mientras existan. El presupuesto alerta a USD 80; no detiene los recursos. No ejecutar el guion k6 de 10k RPS sin dimensionamiento y autorización.
