# Plan e historial de la prueba de 10.000 RPS

**Ejecución completada:** todos los escalones regionales pasaron y los recursos temporales se retiraron. Ver [resultado final](capacity-results.md). Los apartados siguientes conservan las revisiones del plan y sus autorizaciones.

## Alcance inicial y evolución del plan

Solo GET /v1/services con JWT Cognito y fixtures, desde k6 en el Mac. No se ejecutan WAF, canary, caída de tarea/AZ ni nuevos bonus en esta fase. No confundir RPS HTTP con transacciones de negocio que agrupan varias llamadas; aquí cada iteración hace una sola solicitud.

El plan Terraform concreto `iac/high-load.tfplan` propone **0 altas, 2 cambios, 0 bajas**:

- Stage existente: throttle 100 → 10.000 RPS; burst 200 → 5.000.
- Autoscaling existente: mínimo 2 → 8 tareas; máximo 4 → 16 tareas, cada una con 0,5 vCPU/1 GiB. Es capacidad provisional de prueba, no un dimensionamiento ya demostrado.

La imagen desplegada y la topología permanecen iguales. El cambio de mínimo obliga a comprobar ocho tareas y targets saludables antes de iniciar. No se depende del autoscaling para llegar desde dos tareas a un pico inmediato. Las políticas de CPU/requests existentes siguen activas y pueden llevar hasta 16 tareas; registrar cuándo alcanzan el máximo, aunque las solicitudes respondan bien.

## Ejecución y detención

1. Aplicar exclusivamente el plan revisado, esperar ocho tareas saludables y comprobar readiness/JWT. No generar carga antes de completar esa verificación.
2. Login Cognito mediante el helper con --capacity-test. El token pasa en memoria al runner; no se escriben JWT ni headers en reportes.
3. Ejecutar escalones independientes de 100, 500, 1.000, 2.500, 5.000 y 10.000 RPS, 60 segundos cada uno. Máximo nominal 1.146.000 solicitudes; puede existir una iteración de borde por escalón. Cada escalón guarda un resumen separado con p95/p99, throughput observado, respuestas válidas, 429, 5xx y dropped_iterations.
4. Detener al primer escalón que falle: errores/JSON inválido ≥0,1%, p95 ≥200 ms o iteraciones descartadas. k6 evalúa abortOnFail tras 10 segundos iniciales; durante ese periodo pueden ocurrir errores antes del corte. No seguir a tasas superiores para ocultar un fallo.
5. El Mac tiene 8 GiB y ocho núcleos reportados; puede limitar al generador. Preasignación de VUs ajustada a 120 ms y máximo a 200 ms de concurrencia por RPS. Detener escalones posteriores si el hijo consume más de 2 GiB de RSS máximo o más de seis equivalentes de núcleo. Si hay saturación, la conclusión será límite del generador por investigar, no capacidad máxima del backend. No se aprovisiona un generador EC2 sin otro plan aprobado.
6. Conservar incluso resultados fallidos. Medir CPU/memoria/ECS/ALB y consultar métricas CloudWatch tras su retraso de publicación. No afirmar escalamiento o saturación solo por un valor configurado.
7. Al terminar o fallar, generar y revisar un plan de retorno con min=2/max=4 y throttle=100/burst=200, misma imagen. Aplicarlo como parte del alcance aprobado, comprobar estabilidad y un plan posterior sin cambios. Revisar desired_count real: Terraform lo ignora porque lo administra autoscaling; si tarda en bajar, esperar y verificar, sin dejar el perfil alto por descuido.

## Costos y límites de interpretación

Estimación antes de créditos: API Gateway ≈USD 1,146 para todos los escalones a USD 1/millón. Catorce tareas extra durante media hora ≈USD 0,1728, más la base existente, logs, LCUs, métricas, almacenamiento y transferencia. Presupuesto incremental propuesto: **USD 5** para una secuencia y su retorno; no existe corte automático exacto. Una repetición, soak prolongado o un generador nuevo necesitan revisión adicional. Fuentes: https://aws.amazon.com/api-gateway/pricing/ y https://aws.amazon.com/fargate/pricing/.

La cuota regional actual de Gateway es 10.000 RPS y burst 5.000. No hay margen sobre el pico y es compartida con otras APIs. Un escalón al límite puede mostrar 429; de ocurrir, detener y evaluar una ampliación de cuota antes de repetir. Esta prueba no solicita un aumento de cuota ni prueba tolerancia a fallos bajo 10k RPS.

Superar el escalón de 10k permitiría reportar el pico medido de ese endpoint durante un minuto, con sus cifras reales. No demuestra 10k sostenidos durante horas, pérdida de AZ, datos reales ni una garantía enterprise.

Referencias de ejecución: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/ y https://grafana.com/docs/k6/latest/using-k6/thresholds/.

## Revisión del intento inicial y repetición propuesta

El primer intento se detuvo a los 12,15 s del escalón de 100 RPS por 6 dropped_iterations. Las 1.185 solicitudes enviadas fueron válidas, sin 429/5xx, p95 132,856 ms. No se ejecutaron escalones mayores. Se conservan report.json y 100.json en evidence/capacity-attempt-1/. No demuestra límite del backend; el arranque inmediato con pocos VUs necesita corregirse antes de interpretar capacidad.

Se propone una sola repetición dentro del mismo presupuesto total incremental de USD 5: por escalón, rampa de calentamiento de 1 RPS al objetivo durante 10 s y luego 60 s al objetivo. Preasignar al menos 100 VUs; a tasas altas se conservan los límites de memoria/CPU del Mac. Se medirán por separado solicitudes válidas/RPS y p95/p99 de la meseta de 60 s. Se mantienen errores <0,1%, p95 <200 ms y cero dropped_iterations; el inicio de la evaluación abortOnFail pasa a 20 s para tener muestras de la meseta. No se borra ni se reclasifica como exitoso el intento inicial.

Máximo nominal de la repetición con calentamiento: 1.241.530 solicitudes; incluyendo las 1.185 del intento inicial, 1.242.715 (≈USD 1,243 en solicitudes Gateway, antes de los demás cargos). Se vuelve a aplicar el mismo perfil temporal, se esperan ocho tareas saludables y al finalizar se restaura otra vez el perfil base. La repetición fue autorizada y ejecutada; ver capacity-results.md. La regla de autorización sigue vigente para cualquier otra secuencia; no se amplía automáticamente el alcance por haber fallado el generador.

## Autorización posterior y generador regional

El usuario autorizó continuar todos los stages sin nuevas aprobaciones manuales mientras duerme. Se conserva el presupuesto incremental total de USD 5; no se quitaron las protecciones del entorno production de GitHub. La nueva fase usa Terraform/SSO con estado separado para un generador temporal EC2 c7g.2xlarge (8 vCPU/16 GiB, USD 0,29/h consultado), SSM sin puertos de entrada, EBS cifrado, IMDSv2 y terminación programada a una hora. Bucket de scripts/resultados privado y cifrado; IAM restringido a esos prefijos, lectura del cliente Cognito del pool de laboratorio y política gestionada SSM.

Se crea un cliente M2M temporal porque el usuario no estará disponible para el navegador. Client secret y JWT solo se capturan en memoria por el driver; el secreto del cliente queda como atributo sensible en el estado Terraform remoto cifrado y nunca en Git, user data, parámetros SSM ni reportes. El authorizer acepta temporalmente ese client_id además del cliente humano original, conservando issuer y scope infra-metrics/read. El perfil de medición preaprovisiona 16 tareas y limita el máximo a 16 para aislar el pico del retraso del autoscaler. No constituye una prueba de reacción automática ni de caída AZ. Al terminar se restaura el perfil habitual y audience original y se destruyen los 14 recursos auxiliares.

Se repiten los escalones y criterios anteriores desde Linux en us-east-1a. La secuencia nominal suma ~1,24 millones de llamadas; los intentos locales anteriores sumaron 462.043. El controlador conserva un techo de trabajo de ~2,5 millones de solicitudes totales para dejar margen al resto de componentes dentro de USD 5; no es un corte automático exacto de facturación. Todo resultado se conserva, incluido un fallo.
