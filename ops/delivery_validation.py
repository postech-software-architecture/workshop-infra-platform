"""Pure checks for institutional report inputs. Never interprets pending flags as proof."""
from urllib.parse import urlparse

def participants(data):
    if not isinstance(data, list):
        raise ValueError('participants must be a list')
    ids = set()
    for person in data:
        if not isinstance(person, dict) or not all(isinstance(person.get(k), str) and person[k].strip() for k in ('name', 'identification')):
            raise ValueError('Each participant needs a name and identification')
        if len(person['name']) > 160 or len(person['identification']) > 80:
            raise ValueError('Participant fields exceed display limits')
        key = person['identification'].strip().casefold()
        if key in ids:
            raise ValueError('Duplicate participant identification')
        ids.add(key)
    return data

def final_inputs(links, people, status):
    participants(people)
    expected = links.get('expected_participants', 5)
    if type(expected) is not int or expected < 1 or len(people) != expected:
        raise ValueError('Complete the expected participant list before generating the final report')
    flags = ['verified_remote_protection','verified_real_integration','verified_mercado_pago_test_account','verified_compensation','verified_cloud_rollout','verified_complete_bdd']
    if not all(links.get(k) is True for k in flags):
        raise ValueError('Final report requires real proofs: CI/protection, integration, Mercado Pago, compensation, rollout and complete BDD')
    repos = links.get('repositories', {})
    if not all(repos.get(k) for k in ('os','billing','execution')):
        raise ValueError('Three service repository links required')
    for value in list(repos.values()) + [links.get('video')]:
        parsed = urlparse(value or '')
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError('Real HTTPS links without credentials required')
    if not all(s['coverage']['LINE'] >= 80 for s in status['services'].values()):
        raise ValueError('Minimum 80 percent LINE coverage per service required')
