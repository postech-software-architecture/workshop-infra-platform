"""HTTP acceptance run for the real services. Requires the explicit demo profile.
Does not start/stop Docker, sign tokens, inject payment success, or access another service's database.
"""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from decimal import Decimal

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:18080')
    args = parser.parse_args()
    config = dict(line.split('=', 1) for line in (BASE / '.env').read_text().splitlines()
                  if '=' in line and not line.startswith('#'))
    password = os.environ.get('DEMO_PASSWORD') or config.get('DEMO_PASSWORD')
    if not password:
        raise RuntimeError('Demo password is missing. Run configure.py and enable compose.demo.yml.')

    def api(method, route, token=None, body=None, headers=None, expected=(200, 202)):
        request_headers = {'Content-Type': 'application/json', **(headers or {})}
        if token:
            request_headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(args.base_url + route,
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                code, content = response.status, response.read()
        except urllib.error.HTTPError as error:
            code, content = error.code, error.read()
        if code not in expected:
            raise RuntimeError(f'{method} {route}: unexpected HTTP {code}')
        return json.loads(content) if content else None

    def login(name):
        return api('POST', '/os/api/auth/login', body={'username': name, 'password': password})['accessToken']

    def wait_for(label, function, predicate):
        end = time.monotonic() + 45
        while time.monotonic() < end:
            try:
                value = function()
                if predicate(value):
                    return value
            except (urllib.error.URLError, RuntimeError):
                pass
            time.sleep(0.5)
        raise RuntimeError('Condition not proven: ' + label)

    admin, mechanic, customer = login('demo-admin'), login('demo-mecanico'), login('demo-cliente')
    stock_route = '/os/api/v1/estoques/50000000-0000-0000-0000-000000000002'
    initial_stock = Decimal(str(api('GET', stock_route, admin)['quantidade']))
    key = str(uuid.uuid4())
    request = {'clienteDocumento': '12345678909', 'veiculoPlaca': 'ABC1D23', 'observacoes': 'Fase 3 - ' + key}
    order = api('POST', '/os/api/v1/ordens-servico', admin, request, {'Idempotency-Key': key})
    duplicate = api('POST', '/os/api/v1/ordens-servico', admin, request, {'Idempotency-Key': key})
    assert duplicate['id'] == order['id'], 'Opening was duplicated'
    route = '/os/api/v1/ordens-servico/' + order['id']
    work_route = '/execution/api/v1/trabalhos/' + order['trabalhoId']
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
        budget_route = '/billing/api/v1/orcamentos/' + closed['orcamentoId']
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
    result = {'at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'osId': final['id'],
              'attemptId': final['attemptId'], 'trabalhoId': final['trabalhoId'],
              'rejectedBudgetId': first['id'], 'approvedBudgetId': second['id'],
              'finalState': final['status'], 'realPayment': False,
              'checks': ['authenticated opening and idempotency', 'diagnostic projection', 'immutable decimal snapshot',
                         'rejection and stock release', 'new budget version', 'approval and single consumption',
                         'repair blocked before payment']}
    directory = BASE / 'evidencias'
    directory.mkdir(exist_ok=True)
    (directory / 'phase3-integration-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
