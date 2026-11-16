"""HTTP acceptance helpers; secrets stay in memory, never in evidence or URLs."""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


def settings(*files):
    values = {}
    for file in files:
        if file and Path(file).is_file():
            for line in Path(file).read_text(encoding='utf-8-sig').splitlines():
                if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    values[key] = value
    values.update(os.environ)
    return values


class ApiError(RuntimeError):
    def __init__(self, method, route, status):
        self.status = status
        super().__init__(f'{method} {route}: unexpected HTTP {status}')


class Client:
    def __init__(self, base_url, layout='public'):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError('API URL must not contain credentials, query or fragment')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')):
            raise RuntimeError('HTTPS required outside localhost')
        if layout not in ('public', 'edge'):
            raise RuntimeError('Unknown API layout')
        self.base_url, self.layout = base_url.rstrip('/'), layout

    def path(self, service, route):
        return ('/' + service if self.layout == 'edge' else '') + route

    def api(self, method, route, token=None, body=None, headers=None, expected=(200, 202)):
        request_headers = {'Content-Type': 'application/json', **(headers or {})}
        if token:
            request_headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(self.base_url + route,
            data=None if body is None else json.dumps(body).encode(), headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                code, content = response.status, response.read()
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            content = b''
        except urllib.error.URLError:
            raise RuntimeError(f'{method} {route}: network failure') from None
        if code not in expected:
            raise ApiError(method, route, code)
        return json.loads(content) if content else None

    def staff(self, username, password):
        if not password:
            raise RuntimeError('Existing DEMO_PASSWORD is required; do not recreate users')
        return self.api('POST', self.path('os', '/api/auth/login'),
            body={'username': username, 'password': password})['accessToken']

    def customer(self, password):
        if self.layout == 'edge':
            return self.staff('demo-cliente', password)
        return self.api('POST', '/api/auth/cpf', body={'cpf': '12345678909'})['accessToken']


def provider_get(path, token):
    if not token:
        raise RuntimeError('MP_ACCESS_TOKEN is required')
    request = urllib.request.Request('https://api.mercadopago.com' + path,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        raise RuntimeError(f'Mercado Pago read-only proof: HTTP {code}') from None
    except urllib.error.URLError:
        raise RuntimeError('Mercado Pago read-only proof: network failure') from None


def verify_test_seller(config):
    if config.get('MP_BASE_URL', 'https://api.mercadopago.com').rstrip('/') != 'https://api.mercadopago.com':
        raise RuntimeError('Real BDD requires the official provider endpoint')
    if not config.get('MP_APPLICATION_ID') or not config.get('MP_SELLER_ID'):
        raise RuntimeError('MP_APPLICATION_ID and MP_SELLER_ID are required')
    user = provider_get('/users/me', config.get('MP_ACCESS_TOKEN'))
    if str(user.get('id')) != str(config['MP_SELLER_ID']) or 'test_user' not in user.get('tags', []) or user.get('site_id') != 'MLB':
        raise RuntimeError('Brazilian test seller identity was not proven')
    return {'testSellerVerified': True, 'sellerId': str(user['id']), 'siteId': user['site_id']}


def wait_for(label, function, predicate, timeout=90):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            value = function()
        except ApiError as error:
            if error.status != 404:
                raise
            time.sleep(1)
            continue
        if predicate(value):
            return value
        if isinstance(value, dict) and value.get('status') in ('COMPENSADA', 'RECUPERACAO_PENDENTE'):
            raise RuntimeError(label + ': order terminated or requires recovery; inspect the Saga')
        time.sleep(1)
    raise RuntimeError('Condition not proven: ' + label)
