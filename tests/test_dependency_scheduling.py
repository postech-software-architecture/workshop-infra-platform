import json
from pathlib import Path
import subprocess
import unittest
import yaml


class DependencySchedulingTest(unittest.TestCase):
    def test_academy_persistent_dependencies_have_priority_without_changing_claims(self):
        root = Path(__file__).resolve().parents[1]
        docs = list(yaml.safe_load_all(subprocess.check_output(
            ['kubectl', 'kustomize', str(root / 'k8s/overlays/academy')], text=True)))
        priority = next(d for d in docs if d['kind'] == 'PriorityClass')
        self.assertNotIn('namespace', priority['metadata'])
        self.assertEqual(1000, priority['value'])
        self.assertFalse(priority['globalDefault'])
        for name in ('rabbit', 'mongo'):
            actual = next(d for d in docs if d['kind'] == 'StatefulSet' and d['metadata']['name'] == name)
            base = next(d for d in yaml.safe_load_all((root / 'k8s/base' / (name + '.yaml')).read_text())
                        if d['kind'] == 'StatefulSet')
            self.assertEqual(priority['metadata']['name'], actual['spec']['template']['spec'].pop('priorityClassName'))
            self.assertEqual(base['spec']['volumeClaimTemplates'], actual['spec']['volumeClaimTemplates'])
            self.assertEqual(base['spec']['template']['spec'], actual['spec']['template']['spec'])


if __name__ == '__main__':
    unittest.main()
