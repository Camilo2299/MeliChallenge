package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func request(h http.Handler, path string) *httptest.ResponseRecorder {
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", path, nil))
	return w
}
func TestHealth(t *testing.T) {
	h := newHandler()
	for path, want := range map[string]string{"/health/live": `{"status":"ok"}`, "/health/ready": `{"dataset":"sample","status":"ready"}`} {
		w := request(h, path)
		if w.Code != 200 || strings.TrimSpace(w.Body.String()) != want {
			t.Fatalf("%s: %d %s", path, w.Code, w.Body.String())
		}
	}
}
func TestServices(t *testing.T) {
	h := newHandler()
	for _, tc := range []struct {
		query, environment string
		count              int
	}{{"", "", 3}, {"?environment=production", "production", 2}, {"?environment=staging", "staging", 1}} {
		w := request(h, "/v1/services"+tc.query)
		var data []Service
		if err := json.Unmarshal(w.Body.Bytes(), &data); err != nil {
			t.Fatal(err)
		}
		if w.Code != 200 || len(data) != tc.count {
			t.Fatalf("%s: %d %s", tc.query, w.Code, w.Body.String())
		}
		for _, s := range data {
			if tc.environment != "" && s.Environment != tc.environment {
				t.Fatal(s)
			}
		}
	}
	w := request(h, "/v1/services/gateway")
	var service Service
	if err := json.Unmarshal(w.Body.Bytes(), &service); err != nil {
		t.Fatal(err)
	}
	if w.Code != 200 || service.ID != "gateway" || service.Availability != 99.99 {
		t.Fatal(w.Body.String())
	}
}
func TestErrors(t *testing.T) {
	h := newHandler()
	for _, tc := range []struct {
		method, path string
		status       int
		code         string
	}{
		{"GET", "/v1/services/missing", 404, "NOT_FOUND"},
		{"GET", "/unknown", 404, "NOT_FOUND"},
		{"GET", "/v1/services?environment=invalid", 422, "VALIDATION_ERROR"},
		{"GET", "/v1/services?environment=", 422, "VALIDATION_ERROR"},
		{"POST", "/v1/services", 405, "HTTP_ERROR"},
	} {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, httptest.NewRequest(tc.method, tc.path, nil))
		var body struct {
			Error struct {
				Code, Message string
				Details       []struct{ Field, Type string }
			}
		}
		if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
			t.Fatal(err)
		}
		if w.Code != tc.status || body.Error.Code != tc.code || body.Error.Message == "" || w.Header().Get("X-Request-ID") == "" {
			t.Fatalf("%s: %d %s", tc.path, w.Code, w.Body.String())
		}
		if tc.status == 422 && (len(body.Error.Details) != 1 || body.Error.Details[0].Field != "query.environment") {
			t.Fatal(body)
		}
		if tc.status == 405 && w.Header().Get("Allow") != "GET" {
			t.Fatal("missing Allow")
		}
	}
}
func TestDeployments(t *testing.T) {
	h := newHandler()
	for _, tc := range []struct {
		query string
		count int
	}{{"", 2}, {"?service_id=gateway", 1}, {"?service_id=missing", 0}, {"?service_id=", 0}} {
		w := request(h, "/v1/deployments"+tc.query)
		var data []Deployment
		if err := json.Unmarshal(w.Body.Bytes(), &data); err != nil {
			t.Fatal(err)
		}
		if w.Code != 200 || data == nil || len(data) != tc.count {
			t.Fatal(w.Body.String())
		}
		if tc.count == 1 && data[0].ServiceID != "gateway" {
			t.Fatal(data)
		}
	}
}
func TestSummary(t *testing.T) {
	w := request(newHandler(), "/v1/summary")
	var body struct {
		Total       int            `json:"total_services"`
		Statuses    map[string]int `json:"statuses"`
		Source      string         `json:"source"`
		Uptime      float64        `json:"uptime_seconds"`
		GeneratedAt string         `json:"generated_at"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if w.Code != 200 || body.Total != 3 || body.Statuses["healthy"] != 2 || body.Statuses["degraded"] != 1 || body.Statuses["down"] != 0 || body.Source != "sample-data" || body.Uptime < 0 {
		t.Fatal(body)
	}
	if _, err := time.Parse(time.RFC3339Nano, body.GeneratedAt); err != nil {
		t.Fatal(err)
	}
}
func TestRequestHeaders(t *testing.T) {
	h := newHandler()
	for _, id := range []string{"test-123_A.b", "", strings.Repeat("x", 101), "bad id"} {
		r := httptest.NewRequest("GET", "/health/live", nil)
		r.Header.Set("X-Request-ID", id)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		got := w.Header().Get("X-Request-ID")
		if !validRequestID(got) {
			t.Fatalf("invalid response ID %q", got)
		}
		if validRequestID(id) && got != id {
			t.Fatal("valid ID not preserved")
		}
		if !validRequestID(id) && got == id {
			t.Fatal("invalid ID preserved")
		}
		if w.Header().Get("X-Response-Time-Ms") == "" || w.Header().Get("Content-Type") != "application/json" {
			t.Fatal(w.Header())
		}
	}
}
func TestDocumentation(t *testing.T) {
	h := newHandler()
	w := request(h, "/openapi.json")
	var spec struct {
		OpenAPI string
		Paths   map[string]any
	}
	if err := json.Unmarshal(w.Body.Bytes(), &spec); err != nil {
		t.Fatal(err)
	}
	if w.Code != 200 || spec.OpenAPI != "3.0.3" || len(spec.Paths) != 6 {
		t.Fatal(w.Body.String())
	}
	w = request(h, "/docs")
	if w.Code != 200 || !strings.Contains(w.Body.String(), "/openapi.json") || !strings.HasPrefix(w.Header().Get("Content-Type"), "text/html") {
		t.Fatal(w.Body.String())
	}
}
func TestConcurrentRequests(t *testing.T) {
	h := newHandler()
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			w := request(h, "/v1/summary")
			if w.Code != 200 {
				t.Errorf("status %d", w.Code)
			}
		}()
	}
	wg.Wait()
}
func BenchmarkServices(b *testing.B) {
	h := newHandler()
	b.ReportAllocs()
	for b.Loop() {
		request(h, "/v1/services")
	}
}
