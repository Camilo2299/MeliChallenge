# Costo provisional del laboratorio

Supuesto: us-east-1, Linux/x86, dos tareas Fargate de 0,5 vCPU y 1 GiB, dos NAT Gateway y ALB interno. Tarifas públicas consultadas; recalcular al generar el plan real. No se verificó el saldo ni la elegibilidad de los créditos de la cuenta.

| Componente | USD/h | USD/730 h |
|---|---:|---:|
| Dos tareas Fargate | 0.04937 | 36.04 |
| Dos NAT Gateway, cargo horario | 0.09000 | 65.70 |
| Dos IPv4 para NAT | 0.01000 | 7.30 |
| ALB, cargo horario | 0.02250 | 16.43 |
| Subtotal base | 0.17187 | 125.47 |

Base por 24 h: USD 4.12. **No es el total final ni un límite de gasto.** Se suman LCUs, datos procesados por NAT, transferencia, solicitudes API Gateway, Cognito según usuarios/plan, CloudWatch logs/métricas/Container Insights/alarmas, ECR, S3, Secrets Manager y DynamoDB (almacenamiento/PITR y lecturas/escrituras de snapshots). El autoscaling puede aumentar las tareas y un rollout puede duplicar temporalmente el número deseado. El VPC Link no se presupone como recurso gratuito para otros tipos de API/integraciones; verificar la tarifa aplicable del HTTP API elegido.

Los USD 100 de crédito reportados por el usuario no equivalen a presupuesto mensual aprobado. Un mes completo de esta base supera ese crédito. Usar sesiones cortas de laboratorio y revisar destrucción al terminar la demostración; detener ECS no elimina costos de NAT y ALB. La operación destroy está preparada en el pipeline, pero no se ha ejecutado el ciclo destructivo completo. Ver [alcance de retiro](lifecycle.md).

AWS Budgets envía alertas con retraso y no detiene los recursos automáticamente. El bootstrap configura alertas de gasto real y previsto al 100 % del presupuesto configurado; el laboratorio configura USD 80 y correo de alertas mediante el secreto GitHub correspondiente. El presupuesto es de cuenta completa, no solo del proyecto. Debe excluir créditos y reembolsos para hacer visible el consumo bruto.

Fuentes: [Fargate](https://aws.amazon.com/fargate/pricing/), [VPC y NAT/IPv4](https://aws.amazon.com/vpc/pricing/), [ALB](https://aws.amazon.com/elasticloadbalancing/pricing/), [HTTP API](https://aws.amazon.com/api-gateway/pricing/).
