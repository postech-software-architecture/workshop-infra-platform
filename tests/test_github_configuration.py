from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('github_configuration', ROOT / 'ops/configure-github.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class ConfigurationTest(unittest.TestCase):
    def values(self):
        values = {name: name + 'a' * 48 for name in config.GENERATED}
        values.update(RDS_ADMIN_USER='workshop', RDS_ADMIN_PASSWORD='private-admin',
                      RDS_HOST='workshop-db.example.us-east-1.rds.amazonaws.com',
                      AWS_REGION='us-east-1', EKS_CLUSTER_NAME='workshop-eks',
                      STORAGE_CLASS='soat-ebs-gp3')
        return values

    def test_initialize_preserves_existing_secrets_and_imports_mp_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'github.env'
            mp = Path(directory) / 'mp.env'
            mp.write_text('MP_ACCESS_TOKEN=private-mp\nMP_WEBHOOK_SECRET=REPLACE_LOCALLY\n', encoding='utf-8')
            output = io.StringIO()
            with redirect_stdout(output):
                config.initialize(path, import_path=mp)
                first = config.read_env(path)
                config.initialize(path)
            self.assertEqual(first, config.read_env(path))
            generated = [first[name] for name in config.GENERATED]
            self.assertEqual(len(generated), len(set(generated)))
            self.assertTrue(all(len(value) == 48 for value in generated))
            self.assertEqual('private-mp', first['MP_ACCESS_TOKEN'])
            self.assertEqual('', first['MP_WEBHOOK_SECRET'])
            self.assertNotIn('private-mp', output.getvalue())
            self.assertTrue(all(value not in output.getvalue() for value in generated))

    def test_invalid_env_does_not_echo_its_line_and_no_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'github.env'
            path.write_text('TOKEN=$(private_command)\n', encoding='utf-8')
            self.assertEqual('$(private_command)', config.read_env(path)['TOKEN'])
            path.write_text('private-malformed-value\n', encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                config.read_env(path)
            self.assertNotIn('private-malformed-value', str(caught.exception))

    def test_partial_aws_session_fails_before_any_call(self):
        with patch.object(config, 'gh') as gh, self.assertRaises(ValueError):
            config.sync({'AWS_ACCESS_KEY_ID': 'private'}, 'shared', config.ORG, 'prod', True)
        gh.assert_not_called()

    def test_shared_preview_has_no_remote_calls_and_no_values(self):
        values = {name: 'private-' + name for name in config.SHARED}
        output = io.StringIO()
        with patch.object(config, 'gh') as gh, redirect_stdout(output):
            config.sync(values, 'shared', config.ORG, 'prod')
        gh.assert_not_called()
        self.assertTrue(all(value not in output.getvalue() for value in values.values()))

    def test_shared_apply_restricts_repositories_and_uses_separate_stdin(self):
        values = {name: 'private-' + name for name in config.SHARED}
        with patch.object(config, 'gh') as gh, redirect_stdout(io.StringIO()):
            config.sync(values, 'shared', config.ORG, 'prod', True)
        self.assertEqual(4, gh.call_count)
        for call in gh.call_args_list:
            args, value = call.args
            self.assertNotIn(value, args)
            self.assertEqual('selected', args[args.index('--visibility') + 1])
            self.assertEqual(','.join(config.SHARED[args[2]]), args[-1])

    def test_existing_runtime_secret_blocks_all_writes(self):
        with patch.object(config, 'names', return_value={'JWT_SECRET'}), \
                patch.object(config, 'gh') as gh, self.assertRaises(ValueError):
            config.sync(self.values(), 'platform', config.ORG, 'prod', True)
        gh.assert_not_called()

    def test_platform_preview_reads_only_metadata(self):
        with patch.object(config, 'names', return_value=set()), \
                patch.object(config, 'gh') as gh, redirect_stdout(io.StringIO()):
            config.sync(self.values(), 'platform', config.ORG, 'prod')
        gh.assert_not_called()

    def test_confirmed_update_still_checks_password_isolation(self):
        values = self.values()
        values['BILLING_DB_PASSWORD'] = values['OS_DB_PASSWORD']
        with patch.object(config, 'gh') as gh, self.assertRaises(ValueError):
            config.sync(values, 'platform', config.ORG, 'prod', True, True)
        gh.assert_not_called()

    def test_migration_missing_grant_blocks_every_deletion(self):
        with patch.object(config, 'org_access', side_effect=[None, ValueError('missing grant')]), \
                patch.object(config, 'names', return_value=set(config.SHARED)), \
                patch.object(config, 'gh') as gh, self.assertRaises(ValueError):
            config.migrate(config.ORG, 'prod', True)
        gh.assert_not_called()

    def test_migration_only_removes_shared_duplicates(self):
        with patch.object(config, 'org_access'), \
                patch.object(config, 'names', return_value={'AWS_ACCESS_KEY_ID', 'DB_PASSWORD', 'JWT_SECRET'}), \
                patch.object(config, 'gh') as gh, redirect_stdout(io.StringIO()):
            config.migrate(config.ORG, 'prod', True)
        self.assertEqual(2 * len(config.AWS_REPOS), gh.call_count)
        for call in gh.call_args_list:
            self.assertEqual(['secret', 'delete', 'AWS_ACCESS_KEY_ID'], call.args[0][:3])

    def test_private_repo_or_missing_access_prevents_shadow_removal(self):
        for repos in [[], [{'name': 'repo', 'private': True}]]:
            with patch.object(config, 'gh', side_effect=[json.dumps({'visibility': 'selected'}),
                         json.dumps([{'repositories': repos}])]), self.assertRaises(ValueError):
                config.org_access(config.ORG, 'AWS_ACCESS_KEY_ID', ['repo'])

    def test_cli_failure_does_not_expose_stdin_or_cli_debug_output(self):
        result = subprocess.CompletedProcess([], 1, 'private-value', 'private-value')
        with patch.object(config.subprocess, 'run', return_value=result) as run, \
                self.assertRaises(RuntimeError) as caught:
            config.gh(['secret', 'set', 'TOKEN'], 'private-value')
        self.assertNotIn('private-value', str(caught.exception))
        self.assertNotIn('private-value', run.call_args.args[0])
        self.assertEqual('private-value', run.call_args.kwargs['input'])
        self.assertNotIn('GH_DEBUG', run.call_args.kwargs['env'])

    def test_workflow_shared_preflight_reports_only_missing_names(self):
        import yaml
        workflow = yaml.safe_load((ROOT / '.github/workflows/deploy.yml').read_text(encoding='utf-8'))
        step = next(step for step in workflow['jobs']['deploy']['steps']
                    if step.get('name') == 'Check shared credentials')
        with patch.dict(os.environ, {'NEW_RELIC_LICENSE_KEY': 'private-key'}, clear=True), \
                self.assertRaises(SystemExit) as caught:
            exec(compile(step['run'], 'shared-preflight', 'exec'), {})
        self.assertIn('AWS_SESSION_TOKEN', str(caught.exception))
        self.assertNotIn('private-key', str(caught.exception))
        with patch.dict(os.environ, {name: 'private-value' for name in config.SHARED}, clear=True):
            exec(compile(step['run'], 'shared-preflight', 'exec'), {})


if __name__ == '__main__':
    unittest.main()
