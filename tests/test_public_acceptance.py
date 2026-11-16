"""Regression checks for public Auth routes and truthful BDD evidence, without network."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integracao'))
from acceptance_client import ApiError, Client, settings, verify_test_seller, wait_for

spec = importlib.util.spec_from_file_location('bdd_runner', ROOT / 'ops/bdd_runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class PublicAuthenticationTest(unittest.TestCase):
    def test_public_customer_uses_cpf_and_staff_uses_current_login(self):
        client = Client('https://example.test/prod')
        with patch.object(client, 'api', return_value={'accessToken': 'token'}) as api:
            client.staff('demo-admin', 'private-password')
            self.assertEqual('/api/auth/login', api.call_args.args[1])
            client.customer('private-password')
            self.assertEqual('/api/auth/cpf', api.call_args.args[1])
            self.assertEqual({'cpf': '12345678909'}, api.call_args.kwargs['body'])

    def test_legacy_edge_is_explicit_and_public_has_no_service_prefix(self):
        self.assertEqual('/api/v1/pagamentos/id', Client('https://example.test').path('billing', '/api/v1/pagamentos/id'))
        self.assertEqual('/billing/api/v1/pagamentos/id', Client('http://localhost:18080', 'edge').path('billing', '/api/v1/pagamentos/id'))

    def test_secrets_in_url_and_insecure_remote_url_are_rejected(self):
        for url in ('http://remote.test', 'https://user:password@example.test', 'https://example.test?token=private'):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                Client(url)

    def test_http_error_contains_status_without_response_or_token(self):
        error = urllib.error.HTTPError('https://example.test', 403, 'Forbidden', {}, io.BytesIO(b'private-response'))
        with patch('acceptance_client.urllib.request.urlopen', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'unexpected HTTP 403') as caught:
                Client('https://example.test').api('POST', '/api/v1/test', 'private-token')
        self.assertNotIn('private-', str(caught.exception))

    def test_file_is_optional_when_existing_environment_supplies_credential(self):
        with patch.dict(os.environ, {'DEMO_PASSWORD': 'existing'}, clear=True):
            self.assertEqual('existing', settings(Path('missing-demo-config.env'))['DEMO_PASSWORD'])

    def test_async_projection_may_be_temporarily_missing(self):
        with patch('acceptance_client.time.sleep'), patch('acceptance_client.time.monotonic', return_value=0):
            values = iter([ApiError('GET', '/work', 404), {'status': 'READY'}])
            def lookup():
                value = next(values)
                if isinstance(value, Exception):raise value
                return value
            self.assertEqual('READY', wait_for('projection', lookup, lambda v:v['status']=='READY')['status'])

    def test_auth_failure_is_not_hidden_by_async_polling(self):
        with self.assertRaisesRegex(ApiError, '401'):
            wait_for('projection', lambda: (_ for _ in ()).throw(ApiError('GET', '/work', 401)), lambda v:False)

    def test_real_buyer_seller_proof_rejects_non_test_profile_or_wrong_owner(self):
        config = {'MP_ACCESS_TOKEN': 'private-token', 'MP_SELLER_ID': '42', 'MP_APPLICATION_ID': 'app'}
        for user in ({'id': 42, 'tags': [], 'site_id': 'MLB'}, {'id': 43, 'tags': ['test_user'], 'site_id': 'MLB'}):
            with patch('acceptance_client.provider_get', return_value=user), self.assertRaises(RuntimeError):
                verify_test_seller(config)


class CompleteEvidenceTest(unittest.TestCase):
    def run_fixture(self, steps='passed', stale=False, mock=False):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            evidence = Path(directory) / 'evidence'
            target.mkdir(); evidence.mkdir()
            (target / 'bdd-exit.json').write_text(json.dumps({'exitCode': 0}))
            (target / 'cucumber.json').write_text(json.dumps([{'elements': [{'type': 'scenario', 'steps': [{'result': {'status': steps}}]}]}]))
            identity = {'osId': 'order', 'attemptId': 'attempt', 'trabalhoId': 'work', 'runId': 'current', 'passed': True}
            (evidence / 'phase3-integration-results.json').write_text(json.dumps(identity))
            completed = {**identity, 'state': 'ENTREGUE', 'proofKind': 'LOCAL_MOCK' if mock else 'REAL_TEST_PROVIDER',
                'financialAfter': {'testSellerVerified': True}, 'at': '2026-11-16T00:00:00Z'}
            if stale:completed['runId'] = 'older-run'
            (evidence / 'phase4-complete-results.json').write_text(json.dumps(completed))
            with patch.object(runner, 'TARGET', target), patch.object(runner, 'EVIDENCE', evidence), patch.dict(os.environ, {'SOAT_ACCEPTANCE_RUN_ID': 'current'}), patch('builtins.print'):
                runner.finish()
                return json.loads((evidence / 'bdd-complete-summary.json').read_text())

    def test_skipped_step_cannot_be_promoted_as_real_bdd(self):
        with self.assertRaisesRegex(RuntimeError, 'non-skipped'):
            self.run_fixture(steps='skipped')

    def test_old_evidence_or_mock_payment_cannot_pass(self):
        for args in ({'stale': True}, {'mock': True}):
            with self.subTest(args=args), self.assertRaisesRegex(RuntimeError, 'Fresh complete'):
                self.run_fixture(**args)

    def test_real_current_execution_produces_non_dry_run_summary(self):
        self.assertFalse(self.run_fixture()['dryRun'])


if __name__ == '__main__':
    unittest.main()
