# Integração da Fase4

Clonar os quatro repos novos lado a lado. Os contexts deste Compose são ../../workshop-*-service. Consultar ../docs/ACADEMY.md. O Compose é local; Academy usa os overlays e workflows próprios. Verificador histórico e suas evidências foram omitidos. Mercado Pago e SMTP só são habilitados por seus overrides. O BDD requer serviços reais, pagamento assistido e MP_ACCESS_TOKEN/MP_SELLER_ID no ambiente do runner para a consulta independente. Dry-run não é aceite.

## Mercado Pago simulado (somente local)

Enquanto a conta de teste não estiver disponível, `compose.payments-mock.yml` substitui `compose.payments.yml` por um mock da Orders API (QR) em `mercado-pago-mock/server.py`, com os payloads, status, códigos de erro e o webhook assinado (`x-signature`/`x-request-id`, HMAC-SHA256 como nos SDKs oficiais) da documentação. O código do Billing não muda: o mock compartilha o namespace de rede do Billing e atende em `localhost:8090`.

Os Dockerfiles copiam `target/*.jar`: antes do `--build`, rode `mvn -B package -DskipTests` (Java 21) em cada serviço. O gateway local usa os prefixos `/os`, `/billing` e `/execution`, por isso os scripts exigem `--api-layout edge`.

```bash
python3 configure.py
export COMPOSE_FILE=compose.yml:compose.demo.yml:compose.payments-mock.yml
docker compose up -d --build
export MP_BASE_URL=http://127.0.0.1:18090 MP_SELLER_ID=1403498245 MP_APPLICATION_ID=7364289770550796 \
  MP_ACCESS_TOKEN=TEST-0000000000000000-000000-mock000000000000000000000000-000000000
python3 verify-phase3.py --api-layout edge                 # OS aguardando pagamento
curl -s http://127.0.0.1:18090/__mock/orders               # order criada pelo Billing
curl -s -X POST http://127.0.0.1:18090/__mock/orders/ORD.../pay   # ou /reject, /expire
python3 verify-phase4.py --api-layout edge --os-id <osId> --action complete --deliver   # ou --action cancel
```

`MP_MOCK_AUTO_PAY_SECONDS=5` paga automaticamente cada order nova, permitindo rodar o BDD sem comprador (`MP_BASE_URL`, `MP_ACCESS_TOKEN` e `MP_SELLER_ID` acima no ambiente). As rotas `/__mock` não existem na API real. O mock não substitui a prova com conta de teste: o formato do corpo de erro não é documentado pelo Mercado Pago e foi aproximado.

## New Relic (opcional, somente local)

`compose.newrelic.yml` troca o exporter `debug` do coletor por OTLP para o New Relic e lê os logs ECS dos containers. O `trace_parser` copia `traceId`/`spanId` do MDC para o trace context do registro, que é o que o New Relic usa para ligar log e trace (a aba Logs do trace). Os dados chegam com `deployment.environment=local`.

```bash
echo 'NEW_RELIC_LICENSE_KEY=<INGEST - LICENSE>' >> .env
export COMPOSE_FILE=compose.yml:compose.demo.yml:compose.payments-mock.yml:compose.newrelic.yml
docker compose up -d otel
```

Conferência no New Relic: `SELECT count(*) FROM Log WHERE deployment.environment = 'local' AND trace.id IS NOT NULL FACET service.name`. O override não altera o cluster; lá a coleta de logs é feita fora deste repositório.
