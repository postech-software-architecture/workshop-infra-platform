"""HTTP acceptance run for existing demonstration users and the public API.
Does not start/stop Docker, sign tokens, inject payment success, or access another service's database.
"""
import argparse
import json
import os
from pathlib import Path
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse
from acceptance_client import Client, settings, verify_test_seller, wait_for, provider_get

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:18080')
    parser.add_argument('--api-layout', choices=['public', 'edge'], default='public')
    parser.add_argument('--preflight', action='store_true', help='Read-only credentials/API/provider checks; creates no order')
    args = parser.parse_args()
    config = settings(BASE / '.env')
    password = config.get('DEMO_PASSWORD')
    client = Client(args.base_url, args.api_layout)
    api = client.api
    # MP_BASE_URL points the provider proof at the local Orders API mock (compose.payments-mock.yml), as in verify-phase4.py.
    provider_url = config.get('MP_BASE_URL', 'https://api.mercadopago.com').rstrip('/')
    real_provider = provider_url == 'https://api.mercadopago.com'
    if not real_provider and (args.api_layout != 'edge' or urlparse(provider_url).hostname not in ('127.0.0.1', 'localhost')):
        raise SystemExit('Mock provider is only accepted on localhost with --api-layout edge')
    proof = verify_test_seller(config) if real_provider else {'testSellerVerified': False}
    admin = client.staff('demo-admin', password)
    mechanic = client.staff('demo-mecanico', password)
    customer = client.customer(password)
    stock_route = client.path('os', '/api/v1/estoques/50000000-0000-0000-0000-000000000002')
    initial_stock = Decimal(str(api('GET', stock_route, admin)['quantidade']))
    if args.preflight:
        print(json.dumps({'passed': True, 'readOnly': True, 'authenticationVerified': True, **proof}))
        return
    key = str(uuid.uuid4())
    request = {'clienteDocumento': '12345678909', 'veiculoPlaca': 'ABC1D23', 'observacoes': 'BDD Fase 4 - ' + key}
    orders_route = client.path('os', '/api/v1/ordens-servico')
    order = api('POST', orders_route, admin, request, {'Idempotency-Key': key})
    duplicate = api('POST', orders_route, admin, request, {'Idempotency-Key': key})
    assert duplicate['id'] == order['id'], 'Opening was duplicated'
    route = orders_route + '/' + order['id']
    work_route = client.path('execution', '/api/v1/trabalhos/' + order['trabalhoId'])
    work = wait_for('diagnostic admission', lambda: api('GET', work_route, mechanic), lambda w: w['status'] == 'DIAGNOSTICO_PENDENTE')
    work = api('POST', work_route + '/diagnostico/iniciar', mechanic, {}, {'If-Match': str(work['version'])})
    api('POST', work_route + '/diagnostico/concluir', mechanic, {'diagnostico': 'Trocar oleo e filtro'}, {'If-Match': str(work['version'])})
    wait_for('composition', lambda: api('GET', route, admin), lambda o: o['status'] == 'EM_COMPOSICAO')

    def compose():
        for catalog, kind, quantity in [('30000000-0000-0000-0000-000000000001', 'SERVICO', 1),
                                         ('40000000-0000-0000-0000-000000000002', 'INSUMO', 2.5)]:
            item_key = str(uuid.uuid4())
            item = {'catalogoId': catalog, 'tipo': kind, 'quantidade': quantity}
            api('POST', route + '/itens', admin, item, {'Idempotency-Key': item_key})
            api('POST', route + '/itens', admin, item, {'Idempotency-Key': item_key})
        closed = api('POST', route + '/composicao/encerrar', admin, {})
        again = api('POST', route + '/composicao/encerrar', admin, {})
        assert again['orcamentoId'] == closed['orcamentoId']
        wait_for('budget available', lambda: api('GET', route, admin), lambda o: o['status'] == 'AGUARDANDO_APROVACAO')
        budget_route = client.path('billing', '/api/v1/orcamentos/' + closed['orcamentoId'])
        budget = api('GET', budget_route, customer)
        assert budget['snapshot']['totalCentavos'] == 28625
        assert len(budget['snapshot']['itens']) == 2
        return budget_route, budget

    budget_route, first = compose()
    api('POST', budget_route + '/rejeitar', customer, {})
    api('POST', budget_route + '/rejeitar', customer, {})
    wait_for('recomposition', lambda: api('GET', route, admin), lambda o: o['status'] == 'EM_COMPOSICAO' and o['orcamentoVersao'] == 2)
    assert Decimal(str(api('GET', stock_route, admin)['quantidade'])) == initial_stock, 'Release must restore only its reservation'
    api('POST', budget_route + '/aprovar', customer, {}, expected=(422,))
    budget_route, second = compose()
    assert second['id'] != first['id'] and second['snapshot']['orcamentoVersao'] == 2
    api('POST', budget_route + '/aprovar', customer, {})
    api('POST', budget_route + '/aprovar', customer, {})
    final = wait_for('awaiting payment', lambda: api('GET', route, admin), lambda o: o['status'] == 'AGUARDANDO_PAGAMENTO')
    assert Decimal(str(api('GET', stock_route, admin)['quantidade'])) == initial_stock - Decimal('2.5'), 'Approval cannot subtract stock twice'
    work = api('GET', work_route, mechanic)
    api('POST', work_route + '/reparo/iniciar', mechanic, {}, {'If-Match': str(work['version'])}, expected=(422,))
    current = wait_for('provider order creation',
        lambda: api('GET', route, admin), lambda o: bool(o.get('financeiro') and o['financeiro'][0].get('payment_id')))
    payment_id = current['financeiro'][0]['payment_id']
    payment = wait_for('QR linked to this order',
        lambda: api('GET', client.path('billing', '/api/v1/pagamentos/' + payment_id), admin),
        lambda p: bool(p['pagamento'].get('providerOrderId') and p.get('qrData')))
    assert payment['pagamento']['budgetId'] == second['id']
    assert payment['pagamento']['attemptId'] == current['attemptId']
    financial = payment['pagamento']
    resource = provider_get('/v1/orders/' + financial['providerOrderId'], config['MP_ACCESS_TOKEN'], provider_url)
    assert resource['id'] == financial['providerOrderId'] and resource['type'] == 'qr'
    assert str(resource['user_id']) == str(config['MP_SELLER_ID'])
    assert str(resource['integration_data']['application_id']) == str(config['MP_APPLICATION_ID'])
    assert resource['external_reference'] == financial['externalReference']
    assert Decimal(str(resource['total_amount'])) * 100 == financial['totalCentavos'] == 28625
    assert resource['currency'] == financial['moeda'] == 'BRL'
    assert resource['type_response']['qr_data'] == payment['qrData']
    result = {'at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'osId': final['id'],
              'osNumber': final['numero'], 'runId': config.get('SOAT_ACCEPTANCE_RUN_ID', key),
              'attemptId': final['attemptId'], 'trabalhoId': final['trabalhoId'],
              'paymentId': payment_id, 'providerOrderId': payment['pagamento']['providerOrderId'],
              'amountCents': payment['pagamento']['totalCentavos'], 'currency': payment['pagamento']['moeda'],
              'testSellerVerified': proof['testSellerVerified'],
              'providerCreatedAt': resource['created_date'], 'expirationTime': resource.get('expiration_time', 'PT15M'),
              'rejectedBudgetId': first['id'], 'approvedBudgetId': second['id'],
              'finalState': final['status'], 'realPayment': False,
              'checks': ['authenticated opening and idempotency', 'diagnostic projection', 'immutable decimal snapshot',
                         'rejection and stock release', 'new budget version', 'approval and single consumption',
                         'repair blocked before payment']}
    directory = BASE / 'evidencias'
    directory.mkdir(exist_ok=True)
    report = directory / 'phase3-integration-results.json'
    temporary = report.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
    temporary.replace(report)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
