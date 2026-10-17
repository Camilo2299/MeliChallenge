package main

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	cw "github.com/aws/aws-sdk-go-v2/service/cloudwatch/types"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddb "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/ecs"
)

type Observation struct {
	At    time.Time `json:"at"`
	Value float64   `json:"value"`
}
type Metric struct {
	ID         string            `json:"id"`
	Namespace  string            `json:"namespace"`
	Name       string            `json:"name"`
	Unit       string            `json:"unit"`
	Statistic  string            `json:"statistic"`
	Dimensions map[string]string `json:"dimensions"`
	Period     int32             `json:"period_seconds"`
	Points     []Observation     `json:"points"`
	Status     string            `json:"status"`
}
type RealService struct {
	ID             string    `json:"id"`
	Environment    string    `json:"environment"`
	Status         string    `json:"status"`
	Desired        int32     `json:"desired_tasks"`
	Running        int32     `json:"running_tasks"`
	Pending        int32     `json:"pending_tasks"`
	TaskDefinition string    `json:"task_definition"`
	UpdatedAt      time.Time `json:"updated_at"`
}
type RealDeployment struct {
	ID        string     `json:"id"`
	ServiceID string     `json:"service_id"`
	Version   string     `json:"version"`
	Status    string     `json:"status"`
	Rollout   string     `json:"rollout_state"`
	CreatedAt *time.Time `json:"created_at"`
	UpdatedAt *time.Time `json:"updated_at"`
}
type Snapshot struct {
	Source      string           `json:"source"`
	CollectedAt time.Time        `json:"collected_at"`
	Service     RealService      `json:"service"`
	Deployments []RealDeployment `json:"deployments"`
	Metrics     []Metric         `json:"metrics"`
}
type dynamoClient interface {
	UpdateItem(context.Context, *dynamodb.UpdateItemInput, ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error)
	GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	Query(context.Context, *dynamodb.QueryInput, ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
	TransactWriteItems(context.Context, *dynamodb.TransactWriteItemsInput, ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error)
}
type metricsClient interface {
	GetMetricData(context.Context, *cloudwatch.GetMetricDataInput, ...func(*cloudwatch.Options)) (*cloudwatch.GetMetricDataOutput, error)
}
type ecsClient interface {
	DescribeServices(context.Context, *ecs.DescribeServicesInput, ...func(*ecs.Options)) (*ecs.DescribeServicesOutput, error)
}
type telemetry struct {
	table, cluster, service, environment, alb, gateway, key string
	db                                                      dynamoClient
	cw                                                      metricsClient
	ecs                                                     ecsClient
	latest                                                  atomic.Pointer[Snapshot]
	history                                                 atomic.Pointer[[]Snapshot]
}

func newTelemetry(ctx context.Context) (*telemetry, error) {
	if len(os.Getenv("SNAPSHOT_SIGNING_KEY")) < 32 {
		return nil, errors.New("SNAPSHOT_SIGNING_KEY must contain at least 32 characters")
	}
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRetryMaxAttempts(2))
	if err != nil {
		return nil, err
	}
	t := &telemetry{table: os.Getenv("METRICS_TABLE"), cluster: os.Getenv("ECS_CLUSTER"), service: os.Getenv("ECS_SERVICE"), environment: os.Getenv("ENVIRONMENT"), alb: os.Getenv("ALB_DIMENSION"), gateway: os.Getenv("GATEWAY_ID"), key: os.Getenv("SNAPSHOT_SIGNING_KEY"), db: dynamodb.NewFromConfig(cfg), cw: cloudwatch.NewFromConfig(cfg), ecs: ecs.NewFromConfig(cfg)}
	if t.table == "" || t.cluster == "" || t.service == "" || t.alb == "" || t.gateway == "" {
		return nil, errors.New("missing telemetry resource configuration")
	}
	return t, nil
}
func signature(body, key string) string {
	m := hmac.New(sha256.New, []byte(key))
	_, _ = m.Write([]byte(body))
	return hex.EncodeToString(m.Sum(nil))
}
func decodeSnapshot(item map[string]ddb.AttributeValue, key string) (*Snapshot, error) {
	body, ok := item["payload"].(*ddb.AttributeValueMemberS)
	if !ok {
		return nil, errors.New("missing snapshot payload")
	}
	sig, ok := item["signature"].(*ddb.AttributeValueMemberS)
	if !ok || !hmac.Equal([]byte(sig.Value), []byte(signature(body.Value, key))) {
		return nil, errors.New("snapshot integrity check failed")
	}
	var s Snapshot
	if err := json.Unmarshal([]byte(body.Value), &s); err != nil {
		return nil, err
	}
	if s.Source != "aws-cloudwatch-ecs" || s.CollectedAt.IsZero() || s.CollectedAt.After(time.Now().Add(time.Minute)) {
		return nil, errors.New("invalid snapshot metadata")
	}
	return &s, nil
}
func (t *telemetry) keyFor(sk string) map[string]ddb.AttributeValue {
	return map[string]ddb.AttributeValue{"pk": &ddb.AttributeValueMemberS{Value: t.service}, "sk": &ddb.AttributeValueMemberS{Value: sk}}
}
func (t *telemetry) acquire(ctx context.Context, now time.Time) (bool, error) {
	_, err := t.db.UpdateItem(ctx, &dynamodb.UpdateItemInput{TableName: aws.String(t.table), Key: t.keyFor("LOCK"), UpdateExpression: aws.String("SET lease_until = :until"), ConditionExpression: aws.String("attribute_not_exists(lease_until) OR lease_until < :now"), ExpressionAttributeValues: map[string]ddb.AttributeValue{":until": &ddb.AttributeValueMemberN{Value: strconv.FormatInt(now.Add(55*time.Second).Unix(), 10)}, ":now": &ddb.AttributeValueMemberN{Value: strconv.FormatInt(now.Unix(), 10)}}})
	var conflict *ddb.ConditionalCheckFailedException
	if errors.As(err, &conflict) {
		return false, nil
	}
	return err == nil, err
}
func (t *telemetry) specs() []Metric {
	makeMetric := func(id, ns, name, unit, stat string, dims map[string]string) Metric {
		return Metric{ID: id, Namespace: ns, Name: name, Unit: unit, Statistic: stat, Dimensions: dims, Period: 60, Points: []Observation{}, Status: "no_data"}
	}
	e := map[string]string{"ClusterName": t.cluster, "ServiceName": t.service}
	a := map[string]string{"LoadBalancer": t.alb}
	g := map[string]string{"ApiId": t.gateway}
	return []Metric{
		makeMetric("cpu", "AWS/ECS", "CPUUtilization", "Percent", "Average", e), makeMetric("memory", "AWS/ECS", "MemoryUtilization", "Percent", "Average", e),
		makeMetric("alb_requests", "AWS/ApplicationELB", "RequestCount", "Count", "Sum", a), makeMetric("alb_latency", "AWS/ApplicationELB", "TargetResponseTime", "Seconds", "p95", a),
		makeMetric("alb_5xx", "AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "Count", "Sum", a), makeMetric("target_5xx", "AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "Count", "Sum", a),
		makeMetric("gateway_requests", "AWS/ApiGateway", "Count", "Count", "Sum", g), makeMetric("gateway_latency", "AWS/ApiGateway", "Latency", "Milliseconds", "p95", g),
		makeMetric("gateway_4xx", "AWS/ApiGateway", "4xx", "Count", "Sum", g), makeMetric("gateway_5xx", "AWS/ApiGateway", "5xx", "Count", "Sum", g),
	}
}
func (t *telemetry) collect(ctx context.Context) error {
	now := time.Now().UTC()
	acquired, err := t.acquire(ctx, now)
	if err != nil || !acquired {
		return err
	}
	svc, err := t.ecs.DescribeServices(ctx, &ecs.DescribeServicesInput{Cluster: aws.String(t.cluster), Services: []string{t.service}})
	if err != nil {
		return fmt.Errorf("describe service: %w", err)
	}
	if len(svc.Failures) > 0 || len(svc.Services) != 1 {
		return errors.New("configured ECS service unavailable")
	}
	service := svc.Services[0]
	s := Snapshot{Source: "aws-cloudwatch-ecs", CollectedAt: now, Metrics: t.specs(), Deployments: []RealDeployment{}, Service: RealService{ID: t.service, Environment: t.environment, Status: "healthy", Desired: service.DesiredCount, Running: service.RunningCount, Pending: service.PendingCount, TaskDefinition: aws.ToString(service.TaskDefinition), UpdatedAt: now}}
	if service.RunningCount < service.DesiredCount || service.PendingCount > 0 || aws.ToString(service.Status) != "ACTIVE" {
		s.Service.Status = "degraded"
	}
	for _, d := range service.Deployments {
		s.Deployments = append(s.Deployments, RealDeployment{ID: aws.ToString(d.Id), ServiceID: t.service, Version: aws.ToString(d.TaskDefinition), Status: aws.ToString(d.Status), Rollout: string(d.RolloutState), CreatedAt: d.CreatedAt, UpdatedAt: d.UpdatedAt})
	}
	queries := make([]cw.MetricDataQuery, 0, len(s.Metrics))
	for _, m := range s.Metrics {
		dims := []cw.Dimension{}
		for k, v := range m.Dimensions {
			dims = append(dims, cw.Dimension{Name: aws.String(k), Value: aws.String(v)})
		}
		queries = append(queries, cw.MetricDataQuery{Id: aws.String(m.ID), ReturnData: aws.Bool(true), MetricStat: &cw.MetricStat{Metric: &cw.Metric{Namespace: aws.String(m.Namespace), MetricName: aws.String(m.Name), Dimensions: dims}, Period: aws.Int32(60), Stat: aws.String(m.Statistic)}})
	}
	end := now.Truncate(time.Minute)
	result, err := t.cw.GetMetricData(ctx, &cloudwatch.GetMetricDataInput{StartTime: aws.Time(end.Add(-15 * time.Minute)), EndTime: aws.Time(end), MetricDataQueries: queries, ScanBy: cw.ScanByTimestampAscending, MaxDatapoints: aws.Int32(1000)})
	if err != nil {
		return fmt.Errorf("cloudwatch: %w", err)
	}
	if result.NextToken != nil {
		return errors.New("unexpected truncated metric response")
	}
	for i := range s.Metrics {
		m := &s.Metrics[i]
		for _, r := range result.MetricDataResults {
			if aws.ToString(r.Id) != m.ID {
				continue
			}
			if r.StatusCode != cw.StatusCodeComplete {
				m.Status = "partial"
			} else if len(r.Values) > 0 {
				m.Status = "ok"
			}
			for j, v := range r.Values {
				if j < len(r.Timestamps) {
					m.Points = append(m.Points, Observation{At: r.Timestamps[j].UTC(), Value: v})
				}
			}
		}
	}
	body, err := json.Marshal(s)
	if err != nil {
		return err
	}
	sig := signature(string(body), t.key)
	puts := []ddb.TransactWriteItem{}
	for _, sk := range []string{"LATEST", "SNAP#" + now.Format("20060102T150405.000000000Z")} {
		item := t.keyFor(sk)
		item["payload"] = &ddb.AttributeValueMemberS{Value: string(body)}
		item["signature"] = &ddb.AttributeValueMemberS{Value: sig}
		item["expires_at"] = &ddb.AttributeValueMemberN{Value: strconv.FormatInt(now.Add(24*time.Hour).Unix(), 10)}
		puts = append(puts, ddb.TransactWriteItem{Put: &ddb.Put{TableName: aws.String(t.table), Item: item}})
	}
	_, err = t.db.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{TransactItems: puts})
	if err != nil {
		return fmt.Errorf("persist snapshot: %w", err)
	}
	log.Printf("telemetry collection persisted service=%s metrics=%d", t.service, len(s.Metrics))
	return nil
}
func (t *telemetry) refresh(ctx context.Context) error {
	result, err := t.db.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(t.table), Key: t.keyFor("LATEST"), ConsistentRead: aws.Bool(true)})
	if err != nil {
		return err
	}
	if len(result.Item) == 0 {
		return errors.New("no real snapshot yet")
	}
	s, err := decodeSnapshot(result.Item, t.key)
	if err != nil {
		return err
	}
	t.latest.Store(s)
	return nil
}
func (t *telemetry) refreshHistory(ctx context.Context) error {
	r, err := t.db.Query(ctx, &dynamodb.QueryInput{TableName: aws.String(t.table), KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :prefix)"), ExpressionAttributeValues: map[string]ddb.AttributeValue{":pk": &ddb.AttributeValueMemberS{Value: t.service}, ":prefix": &ddb.AttributeValueMemberS{Value: "SNAP#"}}, ScanIndexForward: aws.Bool(false), Limit: aws.Int32(30)})
	if err != nil {
		return err
	}
	h := []Snapshot{}
	for _, item := range r.Items {
		s, e := decodeSnapshot(item, t.key)
		if e != nil {
			return e
		}
		if time.Since(s.CollectedAt) < 24*time.Hour {
			h = append(h, *s)
		}
	}
	t.history.Store(&h)
	return nil
}
func (t *telemetry) run(ctx context.Context) {
	go func() {
		tick := time.NewTicker(time.Minute)
		defer tick.Stop()
		for {
			c, cancel := context.WithTimeout(ctx, 40*time.Second)
			if err := t.collect(c); err != nil {
				log.Printf("telemetry collection failed: %v", err)
			}
			cancel()
			select {
			case <-ctx.Done():
				return
			case <-tick.C:
			}
		}
	}()
	go func() {
		tick := time.NewTicker(3 * time.Second)
		defer tick.Stop()
		n := 0
		for {
			c, cancel := context.WithTimeout(ctx, 2500*time.Millisecond)
			if err := t.refresh(c); err != nil {
				log.Printf("telemetry cache refresh failed: %v", err)
			}
			if n%20 == 0 {
				if err := t.refreshHistory(c); err != nil {
					log.Printf("telemetry history refresh failed: %v", err)
				}
			}
			cancel()
			n++
			select {
			case <-ctx.Done():
				return
			case <-tick.C:
			}
		}
	}()
}

func (t *telemetry) handler(fallback http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/v1/") && r.URL.Path != "/health/ready" {
			fallback.ServeHTTP(w, r)
			return
		}
		started := time.Now()
		id := r.Header.Get("X-Request-ID")
		if !validRequestID(id) {
			id = rand.Text()
		}
		w.Header().Set("X-Request-ID", id)
		w.Header().Set("Cache-Control", "no-store")
		send := func(status int, v any) { writeJSON(w, status, v, started) }
		fail := func(status int, code, msg string) {
			send(status, map[string]any{"error": map[string]string{"code": code, "message": msg}})
		}
		if r.Method != "GET" {
			w.Header().Set("Allow", "GET")
			fail(405, "HTTP_ERROR", "Method Not Allowed")
			return
		}
		path := r.URL.Path
		known := path == "/health/ready" || path == "/v1/services" || path == "/v1/deployments" || path == "/v1/summary" || path == "/v1/metrics" || path == "/v1/metrics/history" || strings.HasPrefix(path, "/v1/services/")
		if !known {
			fail(404, "NOT_FOUND", "Not Found")
			return
		}
		s := t.latest.Load()
		if s == nil {
			fail(503, "TELEMETRY_UNAVAILABLE", "Waiting for a verified AWS snapshot")
			return
		}
		age := time.Since(s.CollectedAt).Seconds()
		stale := age > 180
		w.Header().Set("X-Telemetry-Source", s.Source)
		w.Header().Set("X-Collected-At", s.CollectedAt.Format(time.RFC3339Nano))
		if path == "/health/ready" {
			if age > 300 {
				fail(503, "TELEMETRY_STALE", "AWS snapshot is older than five minutes")
				return
			}
			send(200, map[string]any{"status": "ready", "dataset": "aws", "collected_at": s.CollectedAt, "stale": stale})
			return
		}
		switch path {
		case "/v1/services":
			env := r.URL.Query().Get("environment")
			if r.URL.Query().Has("environment") && env != "lab" && env != "staging" && env != "production" {
				fail(422, "VALIDATION_ERROR", "Invalid environment")
				return
			}
			services := []RealService{}
			if env == "" || env == s.Service.Environment {
				services = append(services, s.Service)
			}
			send(200, services)
		case "/v1/deployments":
			ds := []RealDeployment{}
			if !r.URL.Query().Has("service_id") || r.URL.Query().Get("service_id") == s.Service.ID {
				ds = append(ds, s.Deployments...)
			}
			send(200, ds)
		case "/v1/metrics":
			send(200, s)
		case "/v1/metrics/history":
			h := t.history.Load()
			if h == nil {
				fail(503, "HISTORY_UNAVAILABLE", "History cache is warming up")
				return
			}
			send(200, map[string]any{"source": s.Source, "snapshots": *h, "limit": 30, "retention_hours": 24})
		case "/v1/summary":
			send(200, map[string]any{"source": s.Source, "total_services": 1, "statuses": map[string]int{s.Service.Status: 1}, "collected_at": s.CollectedAt, "age_seconds": age, "stale": stale, "collection_interval_seconds": 60, "cache_refresh_seconds": 3, "metric_count": len(s.Metrics)})
		default:
			if strings.TrimPrefix(path, "/v1/services/") != s.Service.ID {
				fail(404, "NOT_FOUND", "Service not found")
				return
			}
			send(200, s.Service)
		}
	})
}
