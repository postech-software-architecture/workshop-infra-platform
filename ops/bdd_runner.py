"""Run assisted Cucumber acceptance on Actions; publish IDs/reports, never credentials or QR."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BDD = ROOT / 'integracao/bdd'
TARGET = BDD / 'target'
EVIDENCE = ROOT / 'integracao/evidencias'


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def prepare():
    required = ('MP_ACCESS_TOKEN', 'MP_SELLER_ID', 'MP_APPLICATION_ID')
    if any(not os.environ.get(k) for k in required):
        raise RuntimeError('Existing Mercado Pago settings are missing in prod')
    result = subprocess.run(['kubectl', 'get', 'secret', '-n', 'workshop',
        'fase4-demo-credentials', '-o', 'json'], capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError('Cannot read existing demo credentials; no users will be recreated')
    password = base64.b64decode(json.loads(result.stdout)['data']['DEMO_PASSWORD']).decode()
    if not password or '\n' in password or '\r' in password:
        raise RuntimeError('Invalid existing demo credential format')
    print('::add-mask::' + password.replace('%', '%25'))
    config = {'DEMO_PASSWORD': password, **{k: os.environ[k] for k in required}}
    private = ROOT / 'integracao/.env'
    descriptor = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as f:
        for key, value in config.items():
            if '\n' in value or '\r' in value:
                raise RuntimeError('Multiline configuration not supported')
            f.write(key + '=' + value + '\n')
    deployments = subprocess.run(['kubectl', 'get', 'deployment', '-n', 'workshop', '-o', 'json'],
        capture_output=True, check=False)
    if deployments.returncode:
        raise RuntimeError('Cannot inspect deployed service versions')
    images = {item['metadata']['name']: [c['image'] for c in item['spec']['template']['spec']['containers']]
        for item in json.loads(deployments.stdout)['items']
        if item['metadata']['name'] in ('os-service', 'billing-service', 'execucao-service')}
    if len(images) != 3:
        raise RuntimeError('Expected three existing microservice deployments')
    write_json(EVIDENCE / 'runtime-versions.json', {'workflowRunId': os.environ.get('GITHUB_RUN_ID'),
        'acceptanceCommit': os.environ.get('GITHUB_SHA'), 'images': images})
    print('Existing demo credential loaded privately; runtime versions recorded; no infrastructure changed.')


def worker():
    try:
        with (TARGET / 'bdd-run.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(['mvn', '-B', '-ntp', '-Dcucumber.execution.dry-run=false', 'test'],
                cwd=BDD, stdout=log, stderr=subprocess.STDOUT, check=False)
        write_json(TARGET / 'bdd-exit.json', {'exitCode': result.returncode})
    except Exception as error:
        write_json(TARGET / 'bdd-exit.json', {'exitCode': 1, 'failureType': type(error).__name__})


def start():
    TARGET.mkdir(exist_ok=True)
    for p in [TARGET / 'bdd-exit.json', EVIDENCE / 'phase3-integration-results.json',
              EVIDENCE / 'phase4-complete-results.json']:
        p.unlink(missing_ok=True)
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_worker'],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 210
    ready = EVIDENCE / 'phase3-integration-results.json'
    while time.monotonic() < deadline:
        if ready.is_file():
            result = json.loads(ready.read_text(encoding='utf-8'))
            if result.get('runId') != os.environ['SOAT_ACCEPTANCE_RUN_ID'] or not result.get('passed'):
                raise RuntimeError('Fresh preparation evidence not proven')
            safe = {k: result[k] for k in ('osId', 'osNumber', 'attemptId', 'trabalhoId',
                'approvedBudgetId', 'paymentId', 'providerOrderId', 'amountCents', 'currency', 'runId', 'at')}
            write_json(EVIDENCE / 'payment-ready.json', safe)
            print(json.dumps(safe))
            print('Buyer may pay the linked test QR now. No QR or credential is uploaded.')
            return
        if (TARGET / 'bdd-exit.json').is_file():
            raise RuntimeError('BDD ended before payment readiness; inspect acceptance reports')
        time.sleep(1)
    raise RuntimeError('BDD did not prepare an order within the bounded startup time')


def finish():
    deadline = time.monotonic() + 1080
    while time.monotonic() < deadline:
        if (TARGET / 'bdd-exit.json').is_file():
            code = json.loads((TARGET / 'bdd-exit.json').read_text())['exitCode']
            if code:
                raise RuntimeError('Cucumber failed; inspect uploaded reports and sanitized acceptance logs')
            reports = json.loads((TARGET / 'cucumber.json').read_text(encoding='utf-8'))
            scenarios = [s for feature in reports for s in feature.get('elements', []) if s.get('type') == 'scenario']
            if not scenarios or any(not s.get('steps') or any(step.get('result', {}).get('status') != 'passed'
                for step in s['steps']) for s in scenarios):
                raise RuntimeError('Complete non-skipped Cucumber scenario not proven')
            commercial = json.loads((EVIDENCE / 'phase3-integration-results.json').read_text())
            completed = json.loads((EVIDENCE / 'phase4-complete-results.json').read_text())
            if (completed.get('state') != 'ENTREGUE' or completed.get('proofKind') != 'REAL_TEST_PROVIDER'
                or not completed.get('financialAfter', {}).get('testSellerVerified')
                or not completed.get('passed') or not commercial.get('passed')
                or completed.get('runId') != os.environ['SOAT_ACCEPTANCE_RUN_ID']
                or any(completed.get(k) != commercial.get(k) for k in ('osId','attemptId','trabalhoId','runId'))):
                raise RuntimeError('Fresh complete real-payment evidence not proven')
            write_json(EVIDENCE / 'bdd-complete-summary.json', {'passed': True, 'dryRun': False,
                'scenariosPassed': len(scenarios), 'stepsPassed': sum(len(s['steps']) for s in scenarios),
                'workflowRunId': os.environ.get('GITHUB_RUN_ID'), 'commit': os.environ.get('GITHUB_SHA'),
                **{k: completed[k] for k in ('osId','attemptId','trabalhoId','state','runId','proofKind','at')}})
            print('Cucumber real scenario passed; same OS, attempt and work delivered after verified test payment.')
            return
        time.sleep(2)
    raise RuntimeError('Bounded BDD completion time exceeded')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'start', 'finish', '_worker'])
    args = parser.parse_args()
    try:
        {'prepare': prepare, 'start': start, 'finish': finish, '_worker': worker}[args.command]()
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else 'BDD runner failure: ' + type(error).__name__)
        raise SystemExit(1)
