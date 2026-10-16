FROM golang:1.27.2-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY *.go ./
RUN go test ./... && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/infra-signal .

FROM scratch
COPY --from=build /out/infra-signal /infra-signal
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD ["/infra-signal", "healthcheck"]
ENTRYPOINT ["/infra-signal"]
