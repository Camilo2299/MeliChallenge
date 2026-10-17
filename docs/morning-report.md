# Estado final: API con métricas reales

La versión AWS consulta CloudWatch/ECS de nuestra propia infraestructura y persiste snapshots en DynamoDB. La API sirve desde una caché verificada que se actualiza cada tres segundos; la fuente CloudWatch publica muestras por minuto. No se fabrican porcentajes de disponibilidad ni ceros por datos ausentes. El modo local conserva fixtures para desarrollo.

- Vista: https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com/dashboard, con Cognito code + PKCE.
- DynamoDB: `infra-signal-lab-telemetry`, snapshots firmados, TTL 24 h, cifrado y PITR.
- Secrets Manager: `infra-signal-lab/snapshot-signing`, clave HMAC inyectada por ECS. Valor ausente del código, logs, plan y estado Terraform.
- Siete consultas de negocio autenticadas verificadas, dos recolecciones sucesivas y persistencia comprobada. [Reporte funcional](evidence/real-telemetry.json).
- Carga normal: 30 RPS/60 s, 1.801 solicitudes, cero errores/descartes, p95 161 ms desde el Mac.
- Carga regional real: 5.000 RPS/60 s y repetición de 10.000 RPS/30 s, esta última con 300.056 respuestas válidas, p95 8,22 ms y cero errores/descartes.
- El intento real de 10k/60 s **falló** por 1.027 descartes. No se declara superado ni se atribuye su causa sin evidencia suficiente. [Ambos intentos y límites](telemetry-capacity-results.md).

Se restauró el perfil habitual de dos tareas, autoscaling 2–4, throttle 100/burst 200 y audiencia del cliente humano. Los 14 recursos del generador temporal se retiraron; DynamoDB, Secrets Manager y la API permanecen activos. Ver [evidencia de cierre](evidence/real-capacity-restoration.json).

La automatización valida API, persistencia y assets del dashboard. La prueba manual del flujo visual en navegador no se sustituye por esas consultas. No se probó soak prolongado, fallo de AZ bajo carga ni notificación operativa de las alarmas. El benchmark antiguo de fixtures pertenece a otra imagen; no se usa para acreditar la imagen real.

Documentación: [telemetría](telemetry.md), [arquitectura](architecture.md), [capacidad real](telemetry-capacity-results.md) y [checklist](audit.md).
