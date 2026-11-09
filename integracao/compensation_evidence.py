"""Independent acceptance checks. No provider mutation and no database connection."""
from decimal import Decimal
import re

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def paid_reservations(movements, budget):
    records = {}
    for m in movements:
        if m.get('orcamentoId') != budget or m.get('tipo') != 'SAIDA':
            continue
        match = re.fullmatch(r'Consumo da reserva ([0-9a-fA-F-]{36})', m.get('motivo', ''))
        require(match is not None, 'Untraceable consumption movement')
        reservation = match.group(1)
        require(reservation not in records, 'Duplicate reservation consumption')
        quantity = Decimal(str(m['quantidade']))
        require(quantity > 0, 'Invalid movement quantity')
        records[reservation] = {'stock': m['estoqueId'], 'quantity': str(quantity), 'consumptionId': m['id']}
    return records

def verify_stock(records, before, after, movements, budget):
    expected = {key: Decimal(str(value)) for key, value in before.items()}
    reversals = []
    for reservation, record in records.items():
        hits = [m for m in movements if m.get('orcamentoId') == budget and m.get('motivo') == 'Reversao compensatoria da reserva ' + reservation]
        require(len(hits) == 1, 'Reservation needs exactly one compensating movement')
        m = hits[0]
        require(m['tipo'] == 'ENTRADA' and m['estoqueId'] == record['stock'], 'Invalid compensating movement')
        require(Decimal(str(m['quantidade'])) == Decimal(record['quantity']), 'Reversal quantity mismatch')
        require(Decimal(str(m['quantidadePosterior'])) - Decimal(str(m['quantidadeAnterior'])) == Decimal(record['quantity']), 'Reversal balance delta mismatch')
        expected[record['stock']] += Decimal(record['quantity'])
        reversals.append(m['id'])
    require(set(expected) == set(after), 'Stock evidence keys mismatch')
    require(all(Decimal(str(after[k])) == value for k, value in expected.items()), 'Final stock balance mismatch; use an isolated acceptance run')
    require(len(set(reversals)) == len(reversals), 'Reversal movement reused')
    return {'before': before, 'after': after, 'reversalMovementIds': sorted(reversals), 'reservations': records}

def verify_provider(resource, payment, seller, expected):
    require(resource.get('id') == payment['providerOrderId'], 'Provider resource mismatch')
    require(str(resource.get('user_id')) == str(seller), 'Provider seller mismatch')
    require(resource.get('type') == 'qr' and resource.get('currency') == 'BRL', 'Provider type/currency mismatch')
    require(resource.get('external_reference') == payment['externalReference'], 'Provider reference mismatch')
    amount = Decimal(str(resource.get('total_amount', '0'))) * 100
    require(amount == payment['totalCentavos'], 'Provider amount mismatch')
    require(resource.get('live_mode') is not True, 'Test-account proof required')
    if expected == 'CONFIRMADO':
        require(resource.get('status') == 'processed' and resource.get('status_detail') == 'accredited', 'Provider has not confirmed payment')
    elif expected == 'ESTORNADO':
        require(resource.get('status') == 'refunded', 'Provider has not confirmed refund')
    else:
        raise RuntimeError('Unsupported acceptance financial state')
    require(payment['state'] == expected, 'Local financial state mismatch')
    return {'providerOrderId': resource['id'], 'status': resource['status'], 'externalReference': resource['external_reference'], 'totalCentavos': int(amount), 'seller': str(seller)}
