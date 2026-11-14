# Plataforma da Fase 4 — AWS Academy

A plataforma prepara somente recursos runtime adicionais no EKS existente, sem criar IAM/VPC/EKS/RDS. O uso anterior permanece nos seus states. OS e Billing recebem bancos lógicos/usuários separados no RDS atual, com bootstrap restrito, sem substituir a instância nem migrar dados antigos. Mongo e Rabbit têm PVCs de uma réplica usando StorageClass já operacional; não se presume suporte a CSI/IAM que o lab não forneça.

A borda usa um NLB interno novo e proxy com listeners separados: 80 para negócio e 8081 para identidade privada. Não requer ingress-nginx. O API Gateway/VPC Link existente ganha rotas específicas somente mediante corte explícito no repo auth; o fallback antigo é preservado.

`render-academy.py` prepara manifests e confere pré-requisitos existentes. `prepare-secrets.py` monta Secrets de aplicação/infra a partir do ambiente privado, sem imprimir valores. A pipeline manual usa credenciais temporárias e Environment prod; não cria roles para contornar restrições do Academy. CI executa verificações locais sem cloud.

[Runbook de configuração e aceite](docs/ACADEMY.md). Recursos em k8s/base e k8s/overlays/academy. A raiz k8s seleciona Academy. Na distribuição para repos separados também estão integracao/, ops/ e tests/, com Compose opcional para pagamentos/SMTP, BDD, consulta financeira/estoque independente e gerador do PDF.

Verificações locais passaram; integração, rollout, restauração e disponibilidade reais ainda precisam ser comprovados. Nenhuma operação cloud foi executada. PVC não é backup nem garantia de alta disponibilidade. A instância SQL compartilhada não representa isolamento físico entre OS/Billing.
