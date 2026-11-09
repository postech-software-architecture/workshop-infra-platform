"""Acceptance continuation after a real test-account payment. Does not simulate provider confirmation."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from compensation_evidence import require, paid_reservations, verify_stock, verify_provider

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--os-id', required=True, type=uuid.UUID)
    parser.add_argument('--action', choices=['complete', 'cancel'], required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:18080')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--deliver', action='store_true')
    parser.add_argument('--provider-env-file', type=Path, help='Private test-account settings; never stored in evidence')
    args = parser.parse_args()
    if not 10 <= args.timeout <= 1800:
        parser.error('timeout must be between 10 and 1800 seconds')

    def api(method, path, token=None, body=None, version=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if version is not None:
            headers['If-Match'] = str(version)
        request = urllib.request.Request(args.base_url + path, headers=headers, method=method,
                                         data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                content = response.read()
                return json.loads(content) if content else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{method} {path}: HTTP {error.code}') from None

    settings = {}
    for private_file in [BASE / '.env', args.provider_env_file]:
        if private_file and private_file.is_file():
            settings.update(line.split('=', 1) for line in private_file.read_text().splitlines() if '=' in line and not line.startswith('#'))
    settings.update(os.environ)
    provider_token, seller = settings.get('MP_ACCESS_TOKEN'), settings.get('MP_SELLER_ID')
    require(bool(provider_token and seller), 'Real test-account MP_ACCESS_TOKEN and MP_SELLER_ID are required for independent proof')

    admin, mechanic = os.environ.get('ADMIN_ACCESS_TOKEN'), os.environ.get('MECHANIC_ACCESS_TOKEN')
    if not admin or not mechanic:
        env = dict(line.split('=', 1) for line in (BASE / '.env').read_text().splitlines()
                   if '=' in line and not line.startswith('#'))
        password = env['DEMO_PASSWORD']
        admin = api('POST', '/os/api/auth/login', body={'username': 'demo-admin', 'password': password})['accessToken']
        mechanic = api('POST', '/os/api/auth/login', body={'username': 'demo-mecanico', 'password': password})['accessToken']

    route = '/os/api/v1/ordens-servico/' + str(args.os_id)

    def wait(label, function, predicate):
        end = time.monotonic() + args.timeout
        while time.monotonic() < end:
            value = function()
            if predicate(value):
                return value
            if isinstance(value, dict) and value.get('status') == 'RECUPERACAO_PENDENTE':
                raise RuntimeError(label + ': manual recovery is pending; inspect the saga and payment operations')
            time.sleep(1)
        raise RuntimeError('Condition not proven: ' + label)

    order = api('GET', route, admin)
    work_route = '/execution/api/v1/trabalhos/' + order['trabalhoId']
    order = wait('verified payment and repair admission', lambda: api('GET', route, admin),
                 lambda value: value['status'] == 'AGUARDANDO_EXECUCAO')
    payment_id = order['financeiro'][0]['payment_id']
    payment_route = '/billing/api/v1/pagamentos/' + payment_id
    payment = api('GET', payment_route, admin)['pagamento']
    require(payment['budgetId'] == order['orcamentoId'] and payment['attemptId'] == order['attemptId'], 'Payment business context mismatch')

    def financial_proof(expected):
        current = api('GET', payment_route, admin)['pagamento']
        import re
        require(bool(re.fullmatch(r'[A-Za-z0-9_-]{1,128}', current['providerOrderId'])), 'Invalid provider identity')
        request = urllib.request.Request('https://api.mercadopago.com/v1/orders/' + current['providerOrderId'], headers={'Authorization': 'Bearer ' + provider_token})
        with urllib.request.urlopen(request, timeout=6) as response:
            resource = json.load(response)
        return verify_provider(resource, current, seller, expected)

    financial_before = financial_proof('CONFIRMADO')
    stock_evidence = None
    if args.action == 'complete':
        work = api('GET', work_route, mechanic)
        work = api('POST', work_route + '/reparo/iniciar', mechanic, {}, work['version'])
        for task in work['tasks']:
            if task['tipo'] != 'SERVICO':
                continue
            task_route = work_route + '/itens/' + task['itemId']
            work = api('POST', task_route + '/iniciar', mechanic, {}, work['version'])
            work = api('POST', task_route + '/concluir', mechanic, {}, work['version'])
        api('POST', work_route + '/reparo/concluir', mechanic, {}, work['version'])
        order = wait('global technical completion', lambda: api('GET', route, admin), lambda value: value['status'] == 'FINALIZADA')
        if args.deliver:
            order = api('POST', route + '/entregar', admin, {})
    else:
        movement_route = '/os/api/v1/estoques/movimentacoes/ordem-servico/' + str(args.os_id)
        records = paid_reservations(api('GET', movement_route, admin), order['orcamentoId'])
        require(bool(records), 'Use an isolated paid order with consumed parts for compensation acceptance')
        stocks = sorted({item['stock'] for item in records.values()})
        def balances():
            return {stock: str(api('GET', '/os/api/v1/estoques/' + stock, admin)['quantidade']) for stock in stocks}
        before = balances()
        api('POST', route + '/cancelar', admin, {})
        order = wait('confirmed compensation', lambda: api('GET', route, admin), lambda value: value['status'] == 'COMPENSADA')
        require(api('GET', work_route, mechanic)['status'] == 'CANCELADO', 'Technical cancellation unproven')
        wait('local confirmed refund', lambda: api('GET', payment_route, admin)['pagamento'], lambda value: value['state'] == 'ESTORNADO')
        stock_evidence = verify_stock(records, before, balances(), api('GET', movement_route, admin), order['orcamentoId'])
        financial_after = financial_proof('ESTORNADO')
        api('POST', route + '/cancelar', admin, {})
        time.sleep(3)
        repeated = verify_stock(records, before, balances(), api('GET', movement_route, admin), order['orcamentoId'])
        require(repeated == stock_evidence, 'Repeated cancellation changed stock evidence')
        require(financial_proof('ESTORNADO') == financial_after, 'Repeated cancellation changed the provider result')
    progress = api('GET', route + '/saga', admin)
    result = {'at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'osId': str(args.os_id),
              'action': args.action, 'state': order['status'], 'attemptId': order['attemptId'],
              'trabalhoId': order['trabalhoId'], 'progress': progress, 'financialBefore': financial_before,
              'financialAfter': financial_proof('ESTORNADO' if args.action == 'cancel' else 'CONFIRMADO'), 'stockEvidence': stock_evidence}
    (BASE / 'evidencias').mkdir(exist_ok=True)
    (BASE / 'evidencias' / ('phase4-' + args.action + '-results.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
