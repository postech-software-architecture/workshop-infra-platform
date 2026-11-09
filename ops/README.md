# Operação e recuperação

Os comandos abaixo são procedimentos para o ambiente autorizado; não foram executados contra cloud ou contas externas.

1. Consultar `GET /api/v1/ordens-servico/{id}/saga`, `GET /api/v1/pagamentos/{id}` e `GET /api/v1/trabalhos/{id}` com usuário autorizado. Conferir tentativa, orçamento, pagamento, trabalho, erro e histórico antes de retomar.
2. Falha financeira em `MANUAL_REVIEW`: corrigir a configuração ou conferir a divergência no provedor e usar `POST /api/v1/operacoes-financeiras/{id}/retomar` como administrador. A operação conserva sua chave idempotente. Não criar outra operação financeira para contornar timeout.
3. Saga em `RECUPERACAO_PENDENTE`: após tratar o motivo, usar `POST /api/v1/ordens-servico/{id}/saga/retomar` como administrador. A retomada tenta confirmar cancelamento técnico antes de prosseguir com compensação financeira. Se o reparo já começou, sua recusa impede estorno e retorno automático de peças.
4. Se o trabalho técnico pago continuar e concluir durante uma tentativa de cancelamento, seus eventos autorizados permitem convergência da OS sem reposição fictícia de estoque. Uma falha de negócio no reparo físico exige decisão auditada de atendimento; não se tenta desfazer atividade física por rollback de software.
5. Mensagem na DLQ: corrigir a causa e executar `python redrive.py <servico> --limit 1`, com BROKER_ADMIN_URL no ambiente e dependências instaladas. O script publica com confirmação antes de remover a mensagem original. Não registra o corpo nem credenciais. O padrão conserva messageId; reentrega de uma transação já confirmada será ignorada pela inbox.
6. A opção `--new-message-id` é restrita a reconciliação deliberada de um evento antes confirmado/ignorado, depois de conferir o estado atual. Conserva os IDs de negócio e vincula causationId ao evento anterior; não autoriza inventar confirmação de pagamento nem alterar valor/tentativa/versão.

Monitorar readiness, profundidade e idade da outbox, DLQs, operações MANUAL_REVIEW, Sagas em recuperação, latência/erros HTTP e fila técnica. Logs de aplicação usam JSON e correlação; traces e métricas são enviados por OTLP. Logs stdout precisam da coleta já existente no cluster. O collector central possui pipelines OTLP para os três sinais, mas sua publicação New Relic e a coleta dos logs devem ser verificadas no ambiente.

Configuração de tempos atual: timeout HTTP 2 s de conexão/5 s de leitura; polling financeiro 3 s; reconciliação financeira 30 s, retry de falha 1 min e revisão após 10 tentativas; Saga repete comando a cada 1 min, com prazo de 20 min/20 repetições e tick de 30 s. O prazo da cobrança QR é 15 min. A espera de aprovação humana não mantém timer técnico ativo. Ajustar esses valores com a regra de negócio antes da operação final.

Backup/restore: os PVCs são persistentes, mas não substituem backup. Definir snapshots/retention da StorageClass, exportações PostgreSQL, backup Mongo consistente com replica set e políticas/definições Rabbit. Demonstrar uma restauração isolada antes do aceite; não apagar volumes antigos para executar o roteiro novo.

Rollout: usar imagem por SHA. Em falha de readiness, reverter o Deployment; migrations são incrementais e não são revertidas automaticamente. Confirmar compatibilidade do schema antes de retornar uma imagem antiga. Nunca aplicar um destroy geral para corrigir um rollout parcial.
