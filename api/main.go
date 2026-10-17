// Infra Signal serves AWS telemetry when METRICS_TABLE is configured.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

type Service struct {
	ID           string  `json:"id"`
	Environment  string  `json:"environment"`
	Status       string  `json:"status"`
	Availability float64 `json:"availability_pct_24h"`
	UpdatedAt    string  `json:"updated_at"`
}
type Deployment struct {
	ID         string `json:"id"`
	ServiceID  string `json:"service_id"`
	Version    string `json:"version"`
	Result     string `json:"result"`
	DeployedAt string `json:"deployed_at"`
}

var services = []Service{
	{"gateway", "production", "healthy", 99.99, "2026-10-01T10:00:00Z"},
	{"notifications", "production", "degraded", 99.80, "2026-10-01T10:00:00Z"},
	{"billing", "staging", "healthy", 99.95, "2026-10-01T10:00:00Z"},
}
var deployments = []Deployment{
	{"dep-1001", "gateway", "1.4.0", "success", "2026-10-01T08:15:00Z"},
	{"dep-1002", "notifications", "2.1.0", "failed", "2026-10-01T09:05:00Z"},
}

func validRequestID(id string) bool {
	if len(id) == 0 || len(id) > 100 {
		return false
	}
	for _, c := range id {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || strings.ContainsRune("-_.", c)) {
			return false
		}
	}
	return true
}
func writeJSON(w http.ResponseWriter, status int, data any, started time.Time) {
	body, err := json.Marshal(data)
	if err != nil {
		status = 500
		body = []byte(`{"error":{"code":"HTTP_ERROR","message":"Internal server error"}}`)
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Response-Time-Ms", fmt.Sprintf("%.2f", float64(time.Since(started).Microseconds())/1000))
	w.WriteHeader(status)
	_, _ = w.Write(append(body, '\n'))
}
func newHandler() http.Handler {
	boot := time.Now()
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		id := r.Header.Get("X-Request-ID")
		if !validRequestID(id) {
			var b [16]byte
			if _, err := rand.Read(b[:]); err != nil {
				http.Error(w, "Unable to generate request ID", 500)
				return
			}
			id = hex.EncodeToString(b[:])
		}
		w.Header().Set("X-Request-ID", id)
		send := func(status int, data any) { writeJSON(w, status, data, started) }
		fail := func(status int, code, message string) {
			send(status, map[string]any{"error": map[string]string{"code": code, "message": message}})
		}
		path := r.URL.Path
		known := path == "/health/live" || path == "/health/ready" || path == "/v1/services" || path == "/v1/deployments" || path == "/v1/summary" || path == "/docs" || path == "/openapi.json" || strings.HasPrefix(path, "/v1/services/") && len(strings.TrimPrefix(path, "/v1/services/")) > 0 && !strings.Contains(strings.TrimPrefix(path, "/v1/services/"), "/")
		if !known {
			fail(404, "NOT_FOUND", "Not Found")
			return
		}
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			fail(405, "HTTP_ERROR", "Method Not Allowed")
			return
		}
		switch path {
		case "/health/live":
			send(200, map[string]string{"status": "ok"})
		case "/health/ready":
			send(200, map[string]string{"status": "ready", "dataset": "sample"})
		case "/v1/services":
			env := r.URL.Query().Get("environment")
			if r.URL.Query().Has("environment") && env != "production" && env != "staging" {
				send(422, map[string]any{"error": map[string]any{"code": "VALIDATION_ERROR", "message": "Invalid request parameters", "details": []map[string]string{{"field": "query.environment", "type": "literal_error"}}}})
				return
			}
			result := make([]Service, 0, len(services))
			for _, s := range services {
				if env == "" || s.Environment == env {
					result = append(result, s)
				}
			}
			send(200, result)
		case "/v1/deployments":
			result := make([]Deployment, 0, len(deployments))
			filter := r.URL.Query().Get("service_id")
			for _, d := range deployments {
				if !r.URL.Query().Has("service_id") || d.ServiceID == filter {
					result = append(result, d)
				}
			}
			send(200, result)
		case "/v1/summary":
			counts := map[string]int{"healthy": 0, "degraded": 0, "down": 0}
			for _, s := range services {
				counts[s.Status]++
			}
			send(200, map[string]any{"total_services": len(services), "statuses": counts, "source": "sample-data", "uptime_seconds": float64(time.Since(boot).Milliseconds()) / 1000, "generated_at": time.Now().UTC().Format(time.RFC3339Nano)})
		case "/openapi.json":
			send(200, openAPI)
		case "/docs":
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			_, _ = w.Write([]byte(docsHTML))
		default:
			serviceID := strings.TrimPrefix(path, "/v1/services/")
			for _, s := range services {
				if s.ID == serviceID {
					send(200, s)
					return
				}
			}
			fail(404, "NOT_FOUND", fmt.Sprintf("Service '%s' not found", serviceID))
		}
	})
}
func healthcheck() error {
	client := &http.Client{Timeout: 3 * time.Second}
	res, err := client.Get("http://127.0.0.1:8080/health/ready")
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return fmt.Errorf("readiness status %d", res.StatusCode)
	}
	return nil
}
func main() {
	if len(os.Args) == 2 && os.Args[1] == "healthcheck" {
		if err := healthcheck(); err != nil {
			log.Print(err)
			os.Exit(1)
		}
		return
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	var handler http.Handler = newHandler()
	if os.Getenv("METRICS_TABLE") != "" {
		t, err := newTelemetry(ctx)
		if err != nil {
			log.Fatal(err)
		}
		t.run(ctx)
		handler = t.handler(handler)
		log.Print("AWS telemetry enabled; DynamoDB refresh 3s, collection 60s")
	}
	handler = dashboardHandler(handler)
	server := &http.Server{Addr: ":8080", Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 10 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 16 * 1024}
	done := make(chan struct{})
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			log.Printf("shutdown: %v", err)
			_ = server.Close()
		}
		close(done)
	}()
	log.Print("Infra Signal API listening on :8080")
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
	<-done
}
