# Validación local — 13 de octubre de 2026

> Registro histórico del 13 de octubre, anterior a los despliegues y telemetría real. Los pendientes y contenedores mencionados corresponden a esa sesión, no al estado actual. Ver [checklist vigente](audit.md) y [pipelines](lifecycle.md).

Resultados ejecutados en Docker Desktop sobre macOS ARM64:

- `docker build -t infra-signal-api:local ./api`: correcto; incluye `go test ./...` y compilación estática.
- `go test -race -cover ./...` en contenedor `golang:1.27.2`: correcto, cobertura 66,3%; no se detectaron carreras en los tests ejecutados.
- `gofmt -l .` y `go vet ./...` en contenedor Go: correctos.
- Contenedor iniciado con filesystem read-only y `no-new-privileges`, publicado únicamente en `127.0.0.1:18080`.
- Comprobaciones HTTP: health live/ready, listado y detalle de servicios, filtro production, deployments, summary, OpenAPI y docs respondieron 200. Servicio inexistente respondió 404 y filtro inválido 422. Todas las respuestas verificadas incluyeron X-Request-ID.
- `docker exec infra-signal-local-check /infra-signal healthcheck`: correcto.
- Terraform 1.16.5 disponible. `terraform fmt -check -recursive` detectó archivos pendientes de formato. No se ejecutaron init/validate/plan/apply.

La prueba deja el contenedor `infra-signal-local-check` disponible en http://localhost:18080/docs. Para retirarlo tras explorar:

```bash
docker stop infra-signal-local-check
docker rm infra-signal-local-check
```

Go no está disponible en el PATH local; las verificaciones usaron Docker. No se ejecutaron benchmarks comparativos Python/Go, pruebas de 10.000 RPS, failover, despliegue AWS ni rollback. La imagen validada es ARM64 local; falta verificar Linux/amd64 para Fargate antes de publicar.
