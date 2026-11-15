import json
from pathlib import Path
import subprocess
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def evaluate(**scenario):
    config = next(yaml.safe_load_all((ROOT / 'k8s/base/mongo-init.yaml').read_text()))
    raw = subprocess.check_output(['node', str(ROOT / 'tests/mongo-bootstrap-harness.js')],
                                  input=json.dumps({'script':config['data']['init.js'],'scenario':scenario}), text=True)
    return json.loads(raw)


class MongoBootstrapTest(unittest.TestCase):
    def test_only_absent_configuration_is_initialized_and_user_created(self):
        for throws in (False, True):
            result = evaluate(code=94, throwStatus=throws, existing=False, primary=True, user=False)
            self.assertTrue(result['ok'])
            self.assertEqual(['init','createUser'], result['actions'])

    def test_existing_configuration_and_user_password_are_preserved(self):
        result = evaluate(existing=True, primary=True, user=True)
        self.assertTrue(result['ok'])
        self.assertEqual([], result['actions'])
        self.assertTrue(result['output']['existingPasswordsPreserved'])

    def test_existing_config_with_error_or_unexpected_error_cannot_be_overwritten(self):
        for code, existing in ((94,True),(13,False)):
            result = evaluate(code=code, existing=existing, primary=True)
            self.assertFalse(result['ok'])
            self.assertEqual([], result['actions'])

    def test_no_primary_does_not_modify_existing_user(self):
        result = evaluate(existing=True, primary=False, user=True)
        self.assertFalse(result['ok'])
        self.assertEqual([], result['actions'])

    def test_mongo_readiness_checks_primary_and_dns_does_not_depend_on_readiness(self):
        docs = list(yaml.safe_load_all((ROOT / 'k8s/base/mongo.yaml').read_text()))
        self.assertTrue(docs[0]['spec']['publishNotReadyAddresses'])
        probe = docs[1]['spec']['template']['spec']['containers'][0]['readinessProbe']
        self.assertNotIn('tcpSocket', probe)
        self.assertIn('isWritablePrimary', probe['exec']['command'][-1])


if __name__ == '__main__':
    unittest.main()
