package main

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	cw "github.com/aws/aws-sdk-go-v2/service/cloudwatch/types"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddb "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/ecs"
	et "github.com/aws/aws-sdk-go-v2/service/ecs/types"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type fakeDB struct {
	locked bool
	fail   bool
	latest map[string]ddb.AttributeValue
	writes []ddb.TransactWriteItem
}

func (f *fakeDB) UpdateItem(context.Context, *dynamodb.UpdateItemInput, ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error) {
	if f.locked {
		return nil, &ddb.ConditionalCheckFailedException{}
	}
	return &dynamodb.UpdateItemOutput{}, nil
}
func (f *fakeDB) GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	if f.fail {
		return nil, errors.New("unavailable")
	}
	return &dynamodb.GetItemOutput{Item: f.latest}, nil
}
func (f *fakeDB) Query(context.Context, *dynamodb.QueryInput, ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	return &dynamodb.QueryOutput{Items: []map[string]ddb.AttributeValue{f.latest}}, nil
}
func (f *fakeDB) TransactWriteItems(_ context.Context, in *dynamodb.TransactWriteItemsInput, _ ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	f.writes = in.TransactItems
	f.latest = in.TransactItems[0].Put.Item
	return &dynamodb.TransactWriteItemsOutput{}, nil
}

type fakeMetrics struct{ fail bool }

func (f fakeMetrics) GetMetricData(_ context.Context, in *cloudwatch.GetMetricDataInput, _ ...func(*cloudwatch.Options)) (*cloudwatch.GetMetricDataOutput, error) {
	if f.fail {
		return nil, errors.New("cloudwatch unavailable")
	}
	return &cloudwatch.GetMetricDataOutput{MetricDataResults: []cw.MetricDataResult{{Id: aws.String("cpu"), StatusCode: cw.StatusCodeComplete, Timestamps: []time.Time{in.EndTime.Add(-time.Minute)}, Values: []float64{12.5}}, {Id: aws.String("gateway_5xx"), StatusCode: cw.StatusCodeComplete}}}, nil
}

type fakeECS struct{}

func (fakeECS) DescribeServices(context.Context, *ecs.DescribeServicesInput, ...func(*ecs.Options)) (*ecs.DescribeServicesOutput, error) {
	return &ecs.DescribeServicesOutput{Services: []et.Service{{ServiceName: aws.String("infra-signal-lab"), Status: aws.String("ACTIVE"), DesiredCount: 2, RunningCount: 2, TaskDefinition: aws.String("actual:7"), Deployments: []et.Deployment{{Id: aws.String("ecs-svc/actual"), Status: aws.String("PRIMARY"), TaskDefinition: aws.String("actual:7"), RolloutState: et.DeploymentRolloutStateCompleted}}}}}, nil
}
func testTelemetry() (*telemetry, *fakeDB) {
	db := &fakeDB{}
	return &telemetry{table: "test", cluster: "infra-signal-lab", service: "infra-signal-lab", environment: "lab", alb: "app/test/123", gateway: "test", key: strings.Repeat("k", 48), db: db, cw: fakeMetrics{}, ecs: fakeECS{}}, db
}
func TestRealCollectionAndIntegrity(t *testing.T) {
	tm, db := testTelemetry()
	ctx := context.Background()
	if err := tm.collect(ctx); err != nil {
		t.Fatal(err)
	}
	if len(db.writes) != 2 {
		t.Fatal("latest and history must be persisted together")
	}
	if err := tm.refresh(ctx); err != nil {
		t.Fatal(err)
	}
	s := tm.latest.Load()
	if s.Service.ID != "infra-signal-lab" || s.Metrics[0].Points[0].Value != 12.5 || s.Deployments[0].ID != "ecs-svc/actual" {
		t.Fatalf("not real source mapping: %+v", s)
	}
	if len(s.Metrics[9].Points) != 0 || s.Metrics[9].Status != "no_data" {
		t.Fatal("missing error data must not become zero")
	}
	if err := tm.refreshHistory(ctx); err != nil {
		t.Fatal(err)
	}
	db.latest["payload"] = &ddb.AttributeValueMemberS{Value: `{"source":"tampered"}`}
	if err := tm.refresh(ctx); err == nil {
		t.Fatal("tampered snapshot accepted")
	}
	if tm.latest.Load() != s {
		t.Fatal("last verified snapshot was overwritten")
	}
}
func TestCollectorLeaseAndFailures(t *testing.T) {
	tm, db := testTelemetry()
	db.locked = true
	if err := tm.collect(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(db.writes) != 0 {
		t.Fatal("another collector holds lease")
	}
	db.locked = false
	tm.cw = fakeMetrics{fail: true}
	if err := tm.collect(context.Background()); err == nil || len(db.writes) != 0 {
		t.Fatal("must not persist fabricated snapshot on source failure")
	}
}
func TestRealRoutesAndFreshness(t *testing.T) {
	tm, _ := testTelemetry()
	h := tm.handler(newHandler())
	if w := request(h, "/v1/metrics"); w.Code != 503 {
		t.Fatal(w.Code)
	}
	if err := tm.collect(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := tm.refresh(context.Background()); err != nil {
		t.Fatal(err)
	}
	for path, status := range map[string]int{"/v1/services": 200, "/v1/services?environment=lab": 200, "/v1/services?environment=invalid": 422, "/v1/services/infra-signal-lab": 200, "/v1/services/gateway": 404, "/v1/summary": 200, "/v1/metrics": 200, "/v1/metrics/history": 503, "/v1/unknown": 404, "/health/ready": 200} {
		w := request(h, path)
		if w.Code != status || w.Header().Get("X-Request-ID") == "" {
			t.Fatalf("%s %d %s", path, w.Code, w.Body.String())
		}
	}
	w := request(h, "/v1/services?environment=production")
	var data []RealService
	_ = json.Unmarshal(w.Body.Bytes(), &data)
	if len(data) != 0 {
		t.Fatal("must not fabricate production services")
	}
	s := *tm.latest.Load()
	s.CollectedAt = time.Now().Add(-6 * time.Minute)
	tm.latest.Store(&s)
	if request(h, "/health/ready").Code != 503 {
		t.Fatal("stale readiness accepted")
	}
	if request(h, "/health/live").Code != 200 {
		t.Fatal("liveness must be independent")
	}
}
func TestDashboardDoesNotExposeSecret(t *testing.T) {
	t.Setenv("SNAPSHOT_SIGNING_KEY", "never-expose-this")
	h := dashboardHandler(newHandler())
	for _, path := range []string{"/dashboard", "/dashboard.js", "/dashboard/config"} {
		w := request(h, path)
		if w.Code != 200 || strings.Contains(w.Body.String(), "never-expose-this") {
			t.Fatal(path)
		}
		if w.Header().Get("Content-Security-Policy") == "" {
			t.Fatal("missing CSP")
		}
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/dashboard", nil))
	if w.Code != 405 {
		t.Fatal(w.Code)
	}
}
