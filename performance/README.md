# Pruebas de rendimiento y recuperación

La configuración del generador no demuestra throughput: usar el reporte medido y documentar el entorno. Los datos de la API son fixtures.

## Local reproducible

Con Docker Compose o el contenedor local en localhost:18080:

```bash
BASE_URL=http://127.0.0.1:18080 RATE=100 SECONDS=60 K6_NO_USAGE_REPORT=true \
  k6 run --summary-export /tmp/meli-local-load.json performance/loadtest.js
```

Con Compose estándar, cambiar BASE_URL a http://localhost:8080. `RATE` local admite 1–1000 y `SECONDS` 1–60. Criterios: respuestas 200, tres servicios, errores <0,1%, p95 <200 ms y cero iteraciones descartadas. El resultado incluye latencia de red y cliente; no es tiempo de CPU del handler.

## AWS con autorización independiente

Ejecutar el comando de Cognito de run.md agregando `--load-test`: hace un login interactivo, comprueba los cinco requests de negocio y pasa el token al proceso k6 solo mediante el entorno en memoria. La prueba está limitada a 30 RPS durante 60 s, bajo el throttle del stage. No imprimir el entorno ni activar trazas HTTP de headers.

El flag `--resilience-drill` añade el ensayo revisado en docs/validation-plan.md. No usarlo sin autorización: detiene una tarea y cambia temporalmente la revisión del servicio. El flag no constituye autorización por sí mismo. Sin --execute, `cicd/resilience_drill.py` hace únicamente preflight de lectura. El script exige la cuenta, servicio y URL del laboratorio actual; no es una herramienta genérica para producción.

Reportes originales en /tmp/meli-cloud-load.json y /tmp/meli-resilience-drill.json. Las copias revisadas sin tokens se conservan en docs/evidence/. Conservar los resultados fallidos y explicar su causa, no eliminarlos para aparentar éxito.

## Límites

No hay ensayo de 10.000 RPS, caída completa de AZ ni imagen defectuosa. El ensayo de rollback conserva la imagen y configuración conocidas: prueba el cambio de revisión y retorno a la original, no una regresión de negocio. El muestreo de una consulta cada segundo es evidencia puntual, no una garantía de disponibilidad continua. Ver docs/production-readiness.md antes de interpretar estos resultados.
