# BDD completo entre OS, Billing e Execução

Este módulo Cucumber executa abertura idempotente, diagnóstico, composição decimal, orçamento rejeitado, nova versão aprovada, bloqueio de reparo sem pagamento, compra real de teste, reparo e entrega. Preserva OS/tentativa/trabalho e exige ENTREGUE. Não injeta confirmação financeira. Atende ao requisito do PDF: pelo menos um fluxo completo testado com BDD.

Use dados de demonstração, serviços ativos e o comprador de teste no aplicativo. Cada execução cria uma OS e consome 2,5 unidades de insumo; a cobrança é de R$ 286,25. O pagamento é assistido e o QR vence em 15 minutos. Não execute cenários de estoque em paralelo. Não precisa recriar infraestrutura, seeds ou usuários.

## Execução recomendada no GitHub Actions

1. Confirme lab ativo, três credenciais AWS centralizadas válidas e comprador pronto. As configurações MP_ACCESS_TOKEN, MP_SELLER_ID e MP_APPLICATION_ID já devem existir em prod.
2. Em Actions, execute **Complete BDD - real test payment**, na main, com a confirmação **EXECUTAR BDD REAL**. A proteção de prod permanece vigente. O workflow compila antes de criar a OS e lê somente a senha sintética existente no Secret fase4-demo-credentials; não exporta a senha.
3. O Cucumber faz a preparação e publica **bdd-payment-ready**, contendo apenas os IDs da OS/orçamento/pagamento/order. O job continua aguardando a compra. Obtenha o QR pela API autenticada de Billing, GET `/api/v1/pagamentos/{paymentId}`, campo qrData. Gere a imagem localmente e pague com o comprador de teste. Não use uma cobrança avulsa.
4. O executor aguarda confirmação, consulta o recurso oficial de Orders, verifica vendedor test_user, aplicação, tipo QR, moeda, valor e referência e só depois conclui reparo/entrega. Nenhum mock pode passar como prova real.
5. Baixe **bdd-complete-reports**. Confira cucumber.html/json, JUnit XML e bdd-complete-summary.json: passed=true, dryRun=false, todos os steps aprovados e os mesmos IDs terminando em ENTREGUE. O relatório inclui a versão do executor e imagens implantadas. Uma falha ou step pulado não conta como BDD aprovado.

Não há build local, Docker ou WSL nesse procedimento. Collections e environment Postman continuam locais e não são publicados pelo workflow. Artefatos contêm relatórios e IDs sanitizados; senha, tokens e QR não são enviados.

Verificação local SEM acessar serviços (compila e verifica ligação dos steps):

```powershell
mvn -B '-Dcucumber.execution.dry-run=true' test
```

Execução REAL alternativa, a partir desta pasta, com configuração privada existente em `../.env` (DEMO_PASSWORD e as três configurações MP acima), Python e Java 21/Maven disponíveis:

```powershell
$env:SOAT_E2E_ENABLED='true'
$env:SOAT_BASE_URL='https://SEU-API-GATEWAY/prod'
$env:SOAT_API_LAYOUT='public'
$env:SOAT_ACCEPTANCE_RUN_ID=[guid]::NewGuid().ToString()
# Opcional: $env:PYTHON='caminho absoluto do python.exe'
mvn -B test
```

O layout público usa `/api/auth/login`, `/api/auth/cpf` e `/api/v1`, sem prefixos /os, /billing ou /execution. `SOAT_API_LAYOUT=edge` é opção explícita para o gateway local antigo. A verificação real exige o provedor oficial e vendedor de teste. Para conferir previamente sem criar OS: `python ../verify-phase3.py --base-url URL --preflight`.

Relatórios: target/cucumber.html e target/cucumber.json; IDs/estados em ../evidencias/phase3-integration-results.json e phase4-complete-results.json. O CI usa dry-run somente para compilação e ligação dos steps, identificado como **bdd-contract**. Não equivale à execução real manual acima. A execução real nunca reutiliza resultado antigo: exige runId atual e os mesmos IDs nos relatórios recém-gerados.
