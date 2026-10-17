package main

import (
	"embed"
	"encoding/json"
	"net/http"
	"os"
)

//go:embed dashboard.html dashboard.js
var dashboardAssets embed.FS

func dashboardHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/dashboard" && r.URL.Path != "/dashboard.js" && r.URL.Path != "/dashboard/config" {
			next.ServeHTTP(w, r)
			return
		}
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self' https://*.amazoncognito.com; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
		if r.Method != "GET" {
			w.Header().Set("Allow", "GET")
			http.Error(w, "Method Not Allowed", 405)
			return
		}
		if r.URL.Path == "/dashboard/config" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{"client_id": os.Getenv("COGNITO_CLIENT_ID"), "oauth_base": os.Getenv("COGNITO_OAUTH_BASE")})
			return
		}
		file, ct := "dashboard.html", "text/html; charset=utf-8"
		if r.URL.Path == "/dashboard.js" {
			file, ct = "dashboard.js", "text/javascript; charset=utf-8"
		}
		body, err := dashboardAssets.ReadFile(file)
		if err != nil {
			http.Error(w, "Asset unavailable", 500)
			return
		}
		w.Header().Set("Content-Type", ct)
		_, _ = w.Write(body)
	})
}
