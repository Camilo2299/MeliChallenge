# Generador regional temporal

Esta infraestructura se utilizó para el reporte docs/capacity-results.md y ya fue destruida. **No ejecutar apply como parte de un despliegue normal de la API.** La prueba tuvo autorización expresa y presupuesto incremental total de USD 5; repetirla necesita revisar alcance/costo y contar con autorización vigente.

Componentes: cliente Cognito M2M, bucket privado cifrado/TLS de scripts y resultados, rol EC2 con lectura del cliente del pool de laboratorio, GetObject de scripts y PutObject de resultados, política gestionada SSM, perfil de instancia, SG sin ingreso, launch template y c7g.2xlarge con IMDSv2/EBS cifrado. El user data solo contiene IDs públicos; configura terminación al cabo de una hora. k6 oficial se descarga por HTTPS y se verifica contra checksums del release.

Backend separado: bucket de estado existente, key infra-signal/capacity-generator.tfstate, encrypt=true y use_lockfile=true. Ese estado cifrado contiene el client secret como atributo sensible hasta que se retira el cliente; versiones antiguas del estado pueden conservar el secreto ya inválido. No copiar estado/planes a Git ni imprimir DescribeUserPoolClient.

El ejemplo usa IDs de esta cuenta/subred/pool. Adaptarlo y revisar el plan para otra cuenta. `regional_run.py` obtiene client secret mediante el rol y JWT por client_credentials solo en memoria, ejecuta capacity.js y sube únicamente métricas y logs sanitizados. Los comandos SSM no llevan secretos.

Secuencia operacional usada: aplicar generador → añadir temporalmente capacity_client_id a additional_jwt_audiences y preparar 16 tareas/throttle 10k mediante plan del stack principal → validar salud y M2M → ejecutar los escalones por SSM → descargar evidencias → restaurar stack principal/audience → revisar plan -destroy del generador y aplicarlo → verificar ausencia de diferencias, cliente temporal y costos de cómputo auxiliar. El bucket tiene force_destroy solo para retirar scripts/resultados temporales después de descargarlos. No eliminar el estado bootstrap ni el ECR de entrega.

El rol con DescribeUserPoolClient se limita al pool de laboratorio, no a un client_id: IAM soporta alcance a userpool para esa acción. El cliente humano original no tiene secret. El acceso de SSM al host y los scripts debe tratarse como acceso privilegiado al generador.

Fuente de facturación M2M: https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-cognito-removes-machine-machine-app-client-price-dimension/ (AWS retiró el cargo por app client; siguen cargos por solicitudes de token). EC2 c7g.2xlarge: tarifa consultada USD 0,29/h; más IPv4/EBS y tráfico. El resultado de carga no se debe anunciar como garantía enterprise general.
