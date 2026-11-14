# BDD completo entre OS, Billing e Execução

Este módulo Cucumber executa um fluxo completo pelo gateway HTTP usando os scripts de aceitação: abertura idempotente, diagnóstico, composição decimal, orçamento rejeitado, nova versão aprovada, bloqueio de reparo sem pagamento, pagamento real de teste, reparo e entrega. Os steps verificam identidade da OS/tentativa/trabalho e o estado final ENTREGUE. Não contém adapter fictício nem injeta confirmação financeira.

Pré-requisitos: serviços/bancos/broker ativos, configure.py e perfil demo, Mercado Pago de teste habilitado, comprador de teste e Python disponível. Use ambiente isolado: o cenário cria OS e movimenta estoque; consome 2,5 unidades do insumo demonstrativo. A conta compradora paga o QR enquanto o cenário aguarda até 15 minutos. Isso é uma prova assistida, não um pagamento automatizado. Sem ambiente/consentimento explícito, execução real falha; não pula silenciosamente.

Verificação local SEM acessar serviços (compila e verifica ligação dos steps):

```powershell
mvn -B '-Dcucumber.execution.dry-run=true' test
```

Execução REAL, a partir desta pasta:

```powershell
$env:SOAT_E2E_ENABLED='true'
$env:SOAT_BASE_URL='http://127.0.0.1:18080'
# Opcional: $env:PYTHON='caminho absoluto do python.exe'
mvn -B test
```

Ao imprimir osId, consulte a Saga pela API autenticada de OS para obter payment_id, depois GET /billing/api/v1/pagamentos/{id} para obter qrData. Pague na conta de teste. Não cole tokens/credenciais nos relatórios. O teste aguarda confirmação verificada pelo backend e então conduz o reparo.

Relatórios: target/cucumber.html e target/cucumber.json; IDs/estados em ../evidencias/phase3-integration-results.json e phase4-complete-results.json. Logs locais gerados em target podem conter dados da demonstração e não devem ser publicados sem revisão. Execução dry-run comprova somente compilação/steps; não homologação BDD ponta a ponta. Não acrescentar esse dry-run ao total de testes de negócio como fluxo aprovado.
