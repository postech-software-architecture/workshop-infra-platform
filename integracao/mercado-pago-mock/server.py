"""Local stand-in for the Mercado Pago Orders API (in-person QR) used ONLY by the Compose demo.

Shapes follow the official reference (developers/en/reference/in-person-payments/qr-code/orders):
  POST /v1/orders                 201  type=qr, status created/created, type_response.qr_data
  GET  /v1/orders/{id}            200 | 400 invalid_path_param | 404 order_not_found
  POST /v1/orders/{id}/cancel     200  only from status=created (409 otherwise)
  POST /v1/orders/{id}/refund     201  total refund, empty body, only from status=processed (409 otherwise)
Webhooks follow the "order" topic sample and are signed like the official SDKs:
  x-signature: ts=<ms>,v1=HMAC_SHA256_hex(secret, "id:<data.id>;request-id:<x-request-id>;ts:<ts>;")

The buyer side, which a real test account would perform in the Mercado Pago app, is driven by
mock-only endpoints under /__mock (never part of the real API):
  POST /__mock/orders/{id}/pay      -> processed/accredited + order.processed webhook
  POST /__mock/orders/{id}/reject   -> failed/rejected (no webhook action documented for this)
  POST /__mock/orders/{id}/expire   -> expired/expired + order.expired webhook
  GET  /__mock/orders               -> all orders (debug)
MP_MOCK_AUTO_PAY_SECONDS>0 pays every new order after that delay, so unattended BDD runs work.
The error body shape is not documented by Mercado Pago; {"errors":[{code,message}]} is an approximation.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ['MP_ACCESS_TOKEN']
SELLER = os.environ['MP_SELLER_ID']
APPLICATION = os.environ['MP_APPLICATION_ID']
POS = os.environ['MP_POS_ID']
SECRET = os.environ['MP_WEBHOOK_SECRET']
WEBHOOK_URL = os.environ.get('MP_MOCK_WEBHOOK_URL', '')
AUTO_PAY = float(os.environ.get('MP_MOCK_AUTO_PAY_SECONDS', '0'))
PORT = int(os.environ.get('MP_MOCK_PORT', '8090'))
STATE = os.environ.get('MP_MOCK_STATE_FILE', '')  # survives container recreation with Billing

CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
ORDER_ID = re.compile(r'ORD[0-9A-Z]{26}')
DURATION = re.compile(r'P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)')

lock = threading.RLock()
orders = {}
idempotency = {}


def load():
    if STATE and os.path.isfile(STATE):
        with open(STATE, encoding='utf-8') as source:
            saved = json.load(source)
        orders.update(saved['orders'])
        idempotency.update({key: (value[0], tuple(value[1])) for key, value in saved['idempotency'].items()})


def save():
    if STATE:
        with lock, open(STATE + '.tmp', 'w', encoding='utf-8') as target:
            json.dump({'orders': orders, 'idempotency': idempotency}, target)
        os.replace(STATE + '.tmp', STATE)


def new_id(prefix):
    return prefix + ''.join(secrets.choice(CROCKFORD) for _ in range(26))


def now():
    return datetime.now(timezone.utc)


def iso(moment):
    return moment.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def duration(text):
    match = DURATION.fullmatch(text or '')
    if not match or not any(match.groups()):
        return timedelta(minutes=15)  # documented default when no expiration is set
    hours, minutes, seconds = (int(value or 0) for value in match.groups())
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def transition(order, status, detail, payment_status, payment_detail):
    order['status'], order['status_detail'] = status, detail
    order['last_updated_date'] = iso(now())
    for payment in order['transactions']['payments']:
        payment['status'], payment['status_detail'] = payment_status, payment_detail
    save()


def expire_if_due(order):
    if order['status'] == 'created' and time.time() >= order['_expires_at']:
        transition(order, 'expired', 'expired', 'expired', 'expired')
        notify(order, 'order.expired')


def public(order):
    return {key: value for key, value in order.items() if not key.startswith('_')}


def notify(order, action):
    if not WEBHOOK_URL:
        return
    snapshot = public(order)
    body = {
        'action': action, 'api_version': 'v1', 'application_id': APPLICATION,
        'data': {key: snapshot[key] for key in ('id', 'external_reference', 'status', 'status_detail',
                                                'total_amount', 'transactions', 'type')} | {'version': 2},
        'date_created': iso(now()), 'live_mode': False, 'type': 'order', 'user_id': SELLER,
    }
    request_id = str(uuid.uuid4())
    ts = str(int(time.time() * 1000))
    manifest = f'id:{order["id"]};request-id:{request_id};ts:{ts};'
    signature = hmac.new(SECRET.encode(), manifest.encode(), hashlib.sha256).hexdigest()

    def deliver():
        request = urllib.request.Request(
            f'{WEBHOOK_URL}?data.id={order["id"]}&type=order', data=json.dumps(body).encode(), method='POST',
            headers={'Content-Type': 'application/json', 'x-signature': f'ts={ts},v1={signature}',
                     'x-request-id': request_id})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=22) as response:
                    print(f'webhook {action} {order["id"]} -> {response.status}', flush=True)
                    return
            except Exception as error:  # Mercado Pago retries non-2xx deliveries
                print(f'webhook {action} {order["id"]} attempt {attempt + 1} failed: {error}', flush=True)
                time.sleep(2 ** attempt)

    threading.Thread(target=deliver, daemon=True).start()


def pay(order_id):
    with lock:
        order = orders[order_id]
        expire_if_due(order)
        if order['status'] != 'created':
            return 409, error('action_not_allowed_for_current_state', 'Order is ' + order['status'])
        transition(order, 'processed', 'accredited', 'processed', 'accredited')
        order['total_paid_amount'] = order['total_amount']
        for payment in order['transactions']['payments']:
            payment['paid_amount'] = payment['amount']
            payment['payment_method'] = {'id': 'account_money', 'type': 'account_money', 'installments': 1}
            payment['reference'] = {'id': str(secrets.randbelow(10 ** 11))}
        save()
        notify(order, 'order.processed')
        return 200, public(order)


def error(code, message):
    return {'errors': [{'code': code, 'message': message}]}


class Handler(BaseHTTPRequestHandler):
    server_version = 'mercado-pago-mock'

    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), fmt % args), flush=True)

    def reply(self, status, body):
        content = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def body(self):
        if 'chunked' in (self.headers.get('Transfer-Encoding') or '').lower():
            chunks = []
            while True:
                size = int(self.rfile.readline().split(b';')[0].strip() or b'0', 16)
                if size == 0:
                    while self.rfile.readline() not in (b'\r\n', b'\n', b''):
                        pass  # trailers
                    return b''.join(chunks)
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
        length = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(length) if length else b''

    def authorized(self):
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            self.reply(401, error('unauthorized', 'Invalid access token'))
            return False
        return True

    def order(self, order_id):
        if not ORDER_ID.fullmatch(order_id):
            self.reply(400, error('invalid_path_param', 'The ID must start with ORD followed by 26 characters'))
            return None
        found = orders.get(order_id)
        if found is None:
            self.reply(404, error('order_not_found', 'Order not found'))
            return None
        expire_if_due(found)
        return found

    def idempotent(self, raw, action):
        key = self.headers.get('X-Idempotency-Key')
        if not key:
            self.reply(400, error('empty_required_header', 'X-Idempotency-Key is required'))
            return
        fingerprint = hashlib.sha256(self.path.encode() + b'|' + raw).hexdigest()
        with lock:
            previous = idempotency.get(key)
            if previous and previous[0] != fingerprint:
                self.reply(409, error('idempotency_key_already_used', 'Key used with another request'))
                return
            if previous:
                self.reply(*previous[1])
                return
            status, body = action()
            if status < 500:
                idempotency[key] = (fingerprint, (status, body))
                save()
        self.reply(status, body)

    def do_GET(self):
        if self.path == '/__mock/orders':
            with lock:
                return self.reply(200, [public(order) for order in orders.values()])
        match = re.fullmatch(r'/v1/orders/([^/?]+)', self.path)
        if not match:
            return self.reply(404, error('not_found', 'Unknown route'))
        if not self.authorized():
            return
        with lock:
            found = self.order(match.group(1))
            if found is not None:
                self.reply(200, public(found))

    def do_POST(self):
        raw = self.body()
        mock = re.fullmatch(r'/__mock/orders/([^/?]+)/(pay|reject|expire)', self.path)
        if mock:
            return self.simulate(mock.group(1), mock.group(2))
        if not self.authorized():
            return
        if self.path == '/v1/orders':
            return self.idempotent(raw, lambda: self.create(raw))
        match = re.fullmatch(r'/v1/orders/([^/?]+)/(cancel|refund)', self.path)
        if not match:
            return self.reply(404, error('not_found', 'Unknown route'))
        handler = self.cancel if match.group(2) == 'cancel' else self.refund
        self.idempotent(raw, lambda: handler(match.group(1), raw))

    def create(self, raw):
        try:
            request = json.loads(raw)
        except ValueError:
            return 400, error('bad_request', 'Invalid JSON body')
        amount = request.get('total_amount')
        reference = request.get('external_reference')
        if request.get('type') != 'qr' or not isinstance(amount, str) \
                or not re.fullmatch(r'\d+(\.\d{1,2})?', amount) or not reference or len(reference) > 64:
            return 400, error('property_value', 'type=qr, total_amount and external_reference are required')
        qr = (request.get('config') or {}).get('qr') or {}
        if qr.get('external_pos_id') != POS:
            return 404, error('pos_not_found', 'Point of sale not found')
        created = now()
        order_id = new_id('ORD')
        payments = [{'id': new_id('PAY'), 'amount': payment.get('amount', amount), 'status': 'created',
                     'status_detail': 'ready_to_process'}
                    for payment in (request.get('transactions') or {}).get('payments') or [{'amount': amount}]]
        order = {
            'id': order_id, 'user_id': SELLER, 'type': 'qr', 'external_reference': reference,
            'description': request.get('description', ''), 'expiration_time': request.get('expiration_time', 'PT15M'),
            'processing_mode': 'automatic', 'total_amount': amount, 'country_code': 'BRA',
            'integration_data': {'application_id': APPLICATION}, 'status': 'created', 'status_detail': 'created',
            'currency': 'BRL', 'created_date': iso(created), 'last_updated_date': iso(created),
            'config': {'qr': {'external_pos_id': POS, 'mode': qr.get('mode', 'dynamic')}},
            'transactions': {'payments': payments},
            'type_response': {'qr_data': '00020101021243650016com.mercadolibre0201306364' + order_id + '5204000053039865802BR6304MOCK'},
            '_expires_at': (created + duration(request.get('expiration_time'))).timestamp(),
        }
        with lock:
            orders[order_id] = order
        if AUTO_PAY > 0:
            threading.Timer(AUTO_PAY, lambda: pay(order_id)).start()
        return 201, public(order)

    def cancel(self, order_id, _raw):
        with lock:
            found = self.order(order_id)
            if found is None:
                return 404, error('order_not_found', 'Order not found')
            if found['status'] != 'created':
                return 409, error('order_already_canceled' if found['status'] == 'canceled' else 'cannot_cancel_order',
                                  'Orders can only be canceled via API when status=created')
            transition(found, 'canceled', 'canceled', 'canceled', 'canceled_by_api')
            notify(found, 'order.canceled')
            return 200, public(found)

    def refund(self, order_id, raw):
        if raw.strip():
            return 400, error('unsupported_properties', 'For a total refund, the request body must be empty')
        with lock:
            found = self.order(order_id)
            if found is None:
                return 404, error('order_not_found', 'Order not found')
            if found['status'] == 'refunded':
                return 409, error('order_already_refunded', 'Order already refunded')
            if found['status'] != 'processed':
                return 409, error('cannot_refund_order', 'Only orders with status=processed can be refunded')
            transition(found, 'refunded', 'refunded', 'refunded', 'refunded')
            refunds = [{'id': new_id('REF'), 'transaction_id': payment['id'], 'amount': payment['amount'],
                        'status': 'processed', 'reference_id': payment.get('reference', {}).get('id', '')}
                       for payment in found['transactions']['payments']]
            for payment in found['transactions']['payments']:
                payment['refunded_amount'] = payment['amount']
            found['transactions']['refunds'] = refunds
            notify(found, 'order.refunded')
            return 201, {'id': found['id'], 'status': 'refunded', 'status_detail': 'refunded',
                         'transactions': {'refunds': [refund | {'status': 'processing'} for refund in refunds]}}

    def simulate(self, order_id, action):
        if order_id not in orders:
            return self.reply(404, error('order_not_found', 'Order not found'))
        if action == 'pay':
            return self.reply(*pay(order_id))
        with lock:
            found = orders[order_id]
            if found['status'] != 'created':
                return self.reply(409, error('action_not_allowed_for_current_state', 'Order is ' + found['status']))
            if action == 'reject':
                transition(found, 'failed', 'rejected', 'failed', 'rejected')
            else:
                transition(found, 'expired', 'expired', 'expired', 'expired')
                notify(found, 'order.expired')
            self.reply(200, public(found))


if __name__ == '__main__':
    load()
    print(f'Mercado Pago mock on :{PORT} (auto-pay={AUTO_PAY}s, webhook={WEBHOOK_URL or "off"})', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
