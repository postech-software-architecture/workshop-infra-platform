# Configurar credenciais uma vez

Esta automação não precisa dos merges dos serviços. Não cria recursos AWS, roles IAM,
OIDC, Secrets Manager, rotação de senhas ou deploys. Mantém credenciais temporárias
do Academy e o Environment `prod`. O GitHub CLI autenticado é necessário para publicar.

## Distribuição

| Credencial | Fonte | Consumidores |
|---|---|---|
| AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN | Organization secrets, acesso `selected` | Kubernetes, Database, Platform, Auth, OS, Billing e Execution |
| NEW_RELIC_LICENSE_KEY | Organization secret, acesso `selected` | Kubernetes e Platform |
| Senhas SQL/Rabbit/Mongo e tokens de aplicação | Environment `prod` da Platform | Kubernetes Secrets de cada aplicação |
| MP_* e MAIL_* | Environment `prod` da Platform | Secret do Billing |
| JWT_SECRET e AUTH_SERVICE_TOKEN | Fonte privada original da Platform | Também serão necessários no Auth durante sua implantação |
| DB_PASSWORD do RDS já criado | Environment `prod` de Database | Mesma senha em RDS_ADMIN_PASSWORD da Platform |

Os workflows de OS, Billing e Execution recebem AWS para deploy e usam `GITHUB_TOKEN`
automático para publicação. Não cadastrar senhas SQL, Rabbit, Mongo ou Mercado Pago
nesses três repositórios. GitHub Projects não fornece um escopo de secrets compartilhados.

Organization secrets são administrados por proprietários da organização. Repos privados
não podem consumi-los no GitHub Free. O migrador abaixo admite somente repos públicos;
se houver privado, para antes de remover qualquer cópia. Ambientes e suas proteções
continuam existindo. Nenhuma regra de main é alterada.

## 1. Gerar a configuração privada sem acesso ao GitHub

Na raiz deste repo:

```powershell
python ops/configure-github.py init --rds-host HOST_REAL_DO_RDS --import-env integracao/mercado-pago.env
```

Se o arquivo de Mercado Pago estiver em outro local, usar o caminho correspondente.
Se ainda não existir, omitir `--import-env`. A opção aceita também um `.env` anterior
de integração para reutilizar os segredos originais, antes de gerar os ausentes.

O comando cria `private/github.env`, excluído do Git. Gera 13 senhas/tokens aleatórios
distintos com 48 caracteres hexadecimais. Repetir o comando preserva os valores existentes;
placeholders do arquivo importado são ignorados. Não imprime valores. No POSIX usa modo
0600; no Windows o arquivo herda as ACLs da pasta. Guardar backup privado seguro.

Preencher uma vez nesse arquivo:

- `RDS_ADMIN_PASSWORD`: senha já usada em `DB_PASSWORD` no repo Database. Não gerar outra.
- `RDS_HOST`: hostname sem protocolo ou porta, se não informado no comando.
- AWS e New Relic, somente se quiser publicá-los por CLI; podem ser cadastrados pela UI da organização.
- MP_* e MAIL_* disponíveis. Campos opcionais vazios não são enviados. Webhook aguarda o endpoint HTTPS.

Formato literal `NOME=valor`, sem aspas nem execução de comandos. Não enviar o arquivo
no chat, PR ou artifact. GitHub não permite recuperar o valor de um secret já cadastrado.
Se alguma credencial de runtime já foi usada, importar a configuração original; não
substituí-la por uma recém-gerada.

## 2. Publicar senhas e configurações da plataforma em lote

Autenticar o GitHub CLI com permissão administrativa no repo. O comando de login é
interativo e fica sob controle de quem executa:

```powershell
gh auth login --hostname github.com
python ops/configure-github.py sync --scope platform
python ops/configure-github.py sync --scope platform --apply
```

O primeiro comando `sync` mostra somente nomes e destinos. O segundo publica as quatro
Variables e os Secrets da plataforma pelo stdin, sem valores em argumentos ou logs.
Não depende de os Organization secrets já estarem cadastrados. O deploy, sim, precisará deles.

Se encontrar Secrets de runtime existentes, para antes de escrever. Para repetir após
upload parcial ou reaplicar **o mesmo arquivo original**, usar `--update-existing`:

```powershell
python ops/configure-github.py sync --scope platform --update-existing --apply
```

Essa opção confirma que o arquivo é a fonte original. Não é um mecanismo de rotação:
trocar uma senha no GitHub não altera usuários SQL/Rabbit/Mongo já criados nem suas PVCs.
O utilitário nunca apaga Secrets da plataforma e não sobrescreve um opcional vazio.

## 3. Compartilhados: cadastrar ou renovar uma vez

Pela UI: organização → Settings → Secrets and variables → Actions. Usar os mesmos nomes
da tabela e liberar somente os repos indicados. Ou, com acesso de proprietário via CLI:

```powershell
gh auth refresh --hostname github.com --scopes admin:org
python ops/configure-github.py sync --scope shared
python ops/configure-github.py sync --scope shared --apply
```

Os três campos AWS precisam ser atualizados juntos no arquivo. O utilitário envia o
conjunto preenchido uma vez à organização e configura sua lista de repos. New Relic
pode ficar vazio localmente se já foi cadastrado pela UI. Nenhum secret é enviado para
todos os repositórios da organização.

Na próxima renovação da sessão Academy, editar somente esses três campos e repetir o
`sync --scope shared --apply`. O início/renovação da sessão continua dependendo do Academy.

## 4. Remover cópias antigas que prevalecem sobre a organização

Depois de conferir que os valores centrais estão corretos:

```powershell
python ops/configure-github.py migrate-shared
python ops/configure-github.py migrate-shared --apply
```

O migrador verifica existência e acesso selecionado dos quatro secrets na organização,
confere todos os destinos e lista cópias no nível do repo e em `prod`. Só depois remove
as cópias de AWS/New Relic nesses destinos. Não toca em `DB_PASSWORD` ou outros secrets.
Qualquer falha de leitura/permissão interrompe a preparação antes das exclusões. A migração
não é transacional; em falha de rede durante a remoção, pode ser repetida com segurança.
Não verifica igualdade dos valores: APIs de metadata não revelam segredos.

## 5. Validar o consumo

Depois do merge, executar o deploy manual da Platform quando sua configuração estiver
pronta. O preflight confere os nomes compartilhados antes de autenticar na AWS. O
`configure-aws-credentials` valida a sessão real; ingestão New Relic exige conferir os
dados recebidos no teste de observabilidade. Metadata ou cadastro bem-sucedido não prova
que a credencial está válida. O deploy garante o namespace antes do dry-run de Secrets
para funcionar também em um cluster recém-criado.

## Rotação

Geração inicial, distribuição e rotação são operações diferentes. Esta entrega automatiza
as duas primeiras. Rotação real exige alterar o sistema que autentica, atualizar seus
consumidores e validar conexões. Não é executada por rerun do script ou deploy.
Secrets Manager/RDS gerenciado e OIDC precisam de permissões não presumidas no Academy;
não são pré-requisitos nem fallback desta solução.

Referências: [Organization secrets e CLI](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets),
[precedência](https://docs.github.com/en/actions/reference/security/secrets),
[gh secret set](https://cli.github.com/manual/gh_secret_set).
