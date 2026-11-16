# Plataforma Fase 4 — AWS Academy

Runtime dos três microserviços no EKS existente: bancos lógicos exclusivos no RDS para OS/Billing, Mongo rs0 de Execução, RabbitMQ, proxy de borda e collector. [Arquitetura e evidências consolidadas](https://github.com/postech-software-architecture/soat-architecture/blob/main/docs/architecture/fase4/README.md).

**Validado em 15/11/2026:** rollouts independentes, fluxo com compra/entrega, compensação com estorno real, logs/traces/métricas e [BDD completo](https://github.com/postech-software-architecture/workshop-infra-platform/actions/runs/43780849850), 1 cenário/5 passos, sem dry-run, mesma OS/tentativa/trabalho até ENTREGUE. As provas não são mais apenas locais. SMTP, HA/backup/restauração e correlação de logs ao trace específico não foram comprovados.

## Configuração e operação

[Centralização de Secrets](docs/SECRETS.md), [runbook Academy](docs/ACADEMY.md) e [BDD assistido](integracao/bdd/README.md). AWS/New Relic compartilhados vêm dos Secrets da organização; credenciais dos bancos/serviços/MP ficam no Environment prod desta plataforma, sem replicação manual para todos os repos. Renovar os três secrets AWS por sessão do lab.

`render-academy.py` valida pré-requisitos e prepara recursos adicionais no EKS. `prepare-secrets.py` monta o bundle privado. O deploy manual da plataforma aplica esses recursos; os três serviços mantêm seus próprios deploys. A borda usa NLB interno e listeners de negócio 80/identidade 8081, integrados pelo API Gateway/VPC Link do Auth. A API pública atual usa `/api/auth` e `/api/v1` sem prefixos Compose.

São preservados LabRole, states, VPC/EKS/RDS existentes; não criar IAM/OIDC para contornar restrições do Academy. PostgreSQL compartilha instância física, com bancos lógicos/usuários próprios. Mongo/Rabbit têm uma réplica e PVC; isso não prova HA ou backup. Docker/WSL local não é necessário no roteiro atual. Collections e environment Postman permanecem locais.

## Validações e entrega

- [Cobertura/CI/CD das versões implantadas](https://github.com/postech-software-architecture/soat-architecture/blob/main/docs/architecture/fase4/CONFERENCIA-FINAL.md).
- [BDD real e IDs](https://github.com/postech-software-architecture/soat-architecture/blob/main/docs/architecture/fase4/BDD.md); executor em integracao/bdd e workflow acceptance-bdd.yml. CI bdd-contract verifica somente compilação/bindings, separado da execução real assistida.
- [Observabilidade](https://github.com/postech-software-architecture/soat-architecture/blob/main/docs/architecture/fase4/OBSERVABILIDADE.md) e [matriz de aceite](https://github.com/postech-software-architecture/soat-architecture/blob/main/docs/architecture/fase4/ACEITE-E-ENTREGA.md).
- [Retomada amanhã](https://github.com/postech-software-architecture/soat-architecture/blob/main/docs/architecture/fase4/RETOMADA.md). Vídeo e PDF institucional ficaram para o solicitante; nenhum novo PDF foi gerado nesta consolidação.

Os artifacts antigos e evidências locais anteriores preservam seu contexto histórico. O BDD real tem relatório Cucumber/JUnit e resumo durável no repositório de arquitetura. O caso pago/cancelado não é refeito pelo BDD de entrega; foi provado separadamente na OS 10.
