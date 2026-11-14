@integrated @mercadopago
Feature: Ordem de servico completa entre os tres microsservicos
  Scenario: Atendimento aprovado e pago termina com reparo e entrega
    Given um ambiente integrado de demonstracao explicitamente autorizado
    When abro a OS diagnostico rejeito uma proposta e aprovo sua nova versao
    Then a OS aguarda pagamento e bloqueia o reparo prematuro
    When o comprador paga o QR real de teste e o mecanico conclui o reparo
    Then a mesma OS e entregue com tentativa e trabalho preservados
