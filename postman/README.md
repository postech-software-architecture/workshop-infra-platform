# Validação e demonstração da Fase 4

As cinco collections usam o contrato público do API Gateway. O Runner captura tokens, IDs, chaves de idempotência, versões e contexto da Saga no environment. Não é necessário copiar IDs entre requests. As consultas assíncronas esperam a projeção dos eventos, com limite de 90 consultas. Pare se aparecer uma asserção vermelha; não avance manualmente ignorando um estado obrigatório.

## Primeiro teste, passo a passo

1. Abra **Import** no Postman e selecione os cinco arquivos `*.postman_collection.json`.
2. Importe o environment privado recebido separadamente e selecione **SOAT4 - PRIVADO - usuarios de demonstracao** no canto superior. Esse arquivo contém a senha dos usuários sintéticos já cadastrados; mantenha-o local. Para compartilhar, use apenas `SOAT4.template.postman_environment.json`, sem senha nem tokens, e preencha `demo_password` localmente.
3. Confirme `base_url` do lab atual. O lab precisa estar iniciado e os serviços disponíveis. Não há Docker local neste procedimento.
4. Abra a collection **SOAT4 01**, clique **Run**, marque todas as requests, use **uma iteração** e execute. Use o Runner para o encadeamento; o botão Send isolado não executa o fluxo completo.
5. Veja os resultados dos testes. O fluxo autentica administrador, mecânico e cliente; valida permissões; abre a OS; conclui diagnóstico; compõe e rejeita um orçamento; confere a devolução do estoque; recompõe e aprova; verifica cobrança local e bloqueio de reparo/entrega sem pagamento.
6. Confira no environment `main_os_id`, `main_os_number`, `main_work_id`, `main_budget_id`, `main_payment_id`, `main_correlation_id`. Esses IDs ligam as consultas dos três serviços e os registros da demonstração.
7. Execute **SOAT4 02** inteira. Ela cria outra OS e verifica compensação antes de pagamento: cancelamento técnico, encerramento do orçamento e restituição única do estoque. Esse cenário não demonstra estorno financeiro.

Cada execução das collections 01, 02 e da preparação da 05 cria uma nova OS. A collection 01 aprovada consome 2,5 unidades do estoque de demonstração. Não execute em paralelo: as asserções comparam saldos. Não há limpeza destrutiva automática.

## Mercado Pago e continuação

1. Configure localmente `mp_access_token` e `mp_seller_id` da **conta vendedora de teste**. O caixa usa `mp_pos_id=SOATFASE4CAIXA01`. Nunca compartilhe esse environment, exporte com valores ou mostre credenciais na gravação.
2. Execute **SOAT4 03** depois da 01: confere vendedor de teste, loja, caixa, cobrança no Billing e recusa de webhook sem assinatura. `503` é configuração pendente e não é prova de pagamento; `401` prova apenas a recusa da notificação inválida. Se não existir `main_provider_order_id`, a consulta ao provedor é pulada e o pagamento continua bloqueado.
3. Para a demonstração financeira completa é preciso habilitar o gateway no Billing, configurar credenciais, segredo e evento de webhook de Orders e validar uma cobrança realmente vinculada à OS. Não crie uma cobrança avulsa para apresentá-la como pagamento dessa OS. Se o orçamento já aprovado ficar somente com intenção local, use sua cobrança após ativação e confira `providerOrderId` e `qrData` pela request 04 da collection 03.
4. Pague o QR real com a conta compradora de teste. Aguarde o Billing indicar `CONFIRMADO`. Não envie manualmente um evento financeiro ao Rabbit nem simule uma assinatura para liberar o reparo.
5. Execute **SOAT4 04** inteira: autentica novamente sem apagar a OS da 01; exige confirmação no Billing e no provedor; inicia reparo, executa itens, finaliza e entrega a mesma OS. A primeira verificação interrompe se ainda não houver confirmação real.
6. Para estorno use **SOAT4 05** em duas partes: selecione apenas as pastas **01 e 02** para preparar outra OS; pague o QR dessa OS; depois execute apenas a pasta **03 - Estorno real**, conservando o environment. Ela cancela antes de iniciar reparo e consulta estorno real e estoque. Não rode a collection inteira de novo depois do pagamento: a preparação criaria outra OS.

As collections 04 e 05 após pagamento estão preparadas pelo contrato; sua execução depende de pagamento de teste real. A evidência executada deve indicar explicitamente se ficaram bloqueadas.

## Organização da gravação (limite de 15 minutos)

| Tempo | Mostrar | Evidência |
|---|---|---|
| 0:00–1:20 | Diagrama e repositórios: OS/PostgreSQL, Billing/PostgreSQL, Execução/MongoDB, RabbitMQ e Saga orquestrada | Separação de dados, contratos e compensações |
| 1:20–5:00 | Collection 01: login, OS, diagnóstico, orçamento rejeitado e recomposto, aprovação | Estados, IDs comuns, idempotência e estoque |
| 5:00–7:00 | Collection 03 + compra de teste + início da 04 | Cobrança da mesma OS, QR e confirmação real |
| 7:00–9:00 | Final da 04 | Reparo, itens, finalização e entrega |
| 9:00–11:30 | Collection 05 já preparada/paga; executar pasta 03 | Cancelamento, estorno no provedor e estoque. A 02 serve como ensaio sem pagamento, não substitui essa prova |
| 11:30–13:20 | Workflow de um microserviço: testes, qualidade, cobertura, imagem e rollout Kubernetes | Execução de CI/CD real; não disparar deploy só para o vídeo sem checar o lab |
| 13:20–14:40 | New Relic: trace da OS, logs e métricas | Usar `main_correlation_id`/IDs capturados e contexto `trace_id`; confirmar ingestão previamente |
| 14:40–15:00 | Links e arquitetura final | Repositórios, vídeo e entrega |

Deixe abas e execuções previamente abertas. O Postman não comprova sozinho cobertura ≥80% por serviço, BDD completo, proteção de main, pipeline ou ingestão no New Relic. Mostre essas evidências separadamente. O PDF também pede identificação dos participantes, links, diagrama final e justificativas da Saga, tecnologias e divisão dos serviços no documento de entrega.

## Execução por CLI e relatórios seguros

Instale `newman@6.2.3` em um diretório de runtime. Defina `NEWMAN_MODULE` com o caminho absoluto desse módulo e execute:

```text
node run.cjs 01-microsservicos.postman_collection.json private/SOAT4.private.postman_environment.json reports/01.json
```

O executor usa os mesmos testes do Postman, salva as variáveis atualizadas no environment privado e produz relatório com nomes, status, durações, asserções e IDs de evidência. Não grava corpos, cabeçalhos, senhas ou tokens no relatório. Código de saída diferente de zero indica falha; não remova a asserção para transformar erro em sucesso. Não use o relatório JSON padrão do Newman com essas credenciais, pois ele pode incluir dados das requests.

O workflow `postman-demo.yml` exporta somente a senha dos usuários sintéticos existentes, cifrada com a chave pública RSA do solicitante; não altera usuários, seeds, senhas ou configuração do cluster e não exporta chaves de assinatura ou senhas de bancos. A chave privada fica na máquina do solicitante.
