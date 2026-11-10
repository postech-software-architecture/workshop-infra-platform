from pathlib import Path
import copy, importlib.util, json, os, re, subprocess, sys, tempfile, unittest

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
proof=module('proof',ROOT/'integracao/compensation_evidence.py')
delivery=module('delivery',ROOT/'ops/delivery_validation.py')
secrets_module=module('secret_config',ROOT/'prepare-secrets.py')

class CompensationProofTest(unittest.TestCase):
    def setUp(self):
        self.reservation='10000000-0000-0000-0000-000000000001'
        self.consume={'id':'c1','orcamentoId':'budget','tipo':'SAIDA','motivo':'Consumo da reserva '+self.reservation,'estoqueId':'stock','quantidade':'2.5'}
        self.records=proof.paid_reservations([self.consume],'budget')
        self.reverse={'id':'r1','orcamentoId':'budget','tipo':'ENTRADA','motivo':'Reversao compensatoria da reserva '+self.reservation,'estoqueId':'stock','quantidade':'2.5','quantidadeAnterior':'7.5','quantidadePosterior':'10'}
        self.payment={'providerOrderId':'ORD1','externalReference':'workshop_ref','totalCentavos':1000,'state':'CONFIRMADO'}
        self.provider={'id':'ORD1','user_id':42,'type':'qr','currency':'BRL','external_reference':'workshop_ref','total_amount':'10.00','status':'processed','status_detail':'accredited','live_mode':False}
    def test_fractional_stock_and_unique_reversal(self):
        value=proof.verify_stock(self.records,{'stock':'7.5'},{'stock':'10'},[self.reverse],'budget')
        self.assertEqual(['r1'],value['reversalMovementIds'])
    def test_missing_duplicate_or_mismatched_reversal_is_rejected(self):
        variants=[[],[self.reverse,self.reverse],[dict(self.reverse,quantidade='1')],[dict(self.reverse,quantidadePosterior='11')],[dict(self.reverse,tipo='SAIDA')],[dict(self.reverse,estoqueId='other')]]
        for movements in variants:
            with self.subTest(movements=movements),self.assertRaises(RuntimeError):proof.verify_stock(self.records,{'stock':'7.5'},{'stock':'10'},movements,'budget')
    def test_incorrect_final_balance_is_rejected(self):
        with self.assertRaises(RuntimeError):proof.verify_stock(self.records,{'stock':'7.5'},{'stock':'12.5'},[self.reverse],'budget')
    def test_duplicated_consumption_is_rejected(self):
        with self.assertRaises(RuntimeError):proof.paid_reservations([self.consume,self.consume],'budget')
    def test_provider_confirmation_then_confirmed_refund(self):
        self.assertEqual('processed',proof.verify_provider(self.provider,self.payment,'42','CONFIRMADO')['status'])
        self.provider['status']='refunded';self.payment['state']='ESTORNADO'
        self.assertEqual('refunded',proof.verify_provider(self.provider,self.payment,'42','ESTORNADO')['status'])
    def test_wrong_resource_owner_reference_currency_amount_or_live_mode_rejected(self):
        for key,value in [('id','other'),('user_id',99),('external_reference','other'),('currency','USD'),('total_amount','10.01'),('live_mode',True),('status_detail','pending')]:
            with self.subTest(key=key),self.assertRaises(RuntimeError):proof.verify_provider(dict(self.provider,**{key:value}),self.payment,'42','CONFIRMADO')
    def test_refund_requested_without_confirmation_rejected(self):
        self.payment['state']='ESTORNADO'
        with self.assertRaises(RuntimeError):proof.verify_provider(self.provider,self.payment,42,'ESTORNADO')

class DeliveryInputsTest(unittest.TestCase):
    def setUp(self):
        self.people=[{'name':'Pessoa de teste '+str(i),'identification':'TEST-'+str(i)} for i in range(5)]
        self.links={'expected_participants':5,'repositories':dict.fromkeys(['os','billing','execution'],'https://github.com/example/service'),'video':'https://youtu.be/example'}
        for key in ['verified_remote_protection','verified_real_integration','verified_mercado_pago_test_account','verified_compensation','verified_cloud_rollout','verified_complete_bdd']:self.links[key]=True
        self.status={'services':{'os':{'coverage':{'LINE':80}}}}
    def test_complete_participant_input_is_accepted(self):delivery.final_inputs(self.links,self.people,self.status)
    def test_empty_incomplete_duplicate_or_long_participants_rejected(self):
        for people in [[],self.people[:4],[dict(self.people[0])]*5,[{'name':'A','identification':''}],[{'name':'A'*161,'identification':'X'}]]:
            with self.subTest(people=people),self.assertRaises(ValueError):delivery.final_inputs(self.links,people,self.status)
    def test_dry_run_cannot_replace_complete_bdd_evidence(self):
        self.links['verified_complete_bdd']=False
        with self.assertRaises(ValueError):delivery.final_inputs(self.links,self.people,self.status)
    def test_nonliteral_true_link_credentials_or_insufficient_coverage_rejected(self):
        invalid=[dict(self.links,verified_compensation='true'),dict(self.links,video='http://youtu.be/test'),dict(self.links,video='https://secret:password@example.com')]
        for links in invalid:
            with self.subTest(links=links),self.assertRaises(ValueError):delivery.final_inputs(links,self.people,self.status)
        self.status['services']['os']['coverage']['LINE']=79.99
        with self.assertRaises(ValueError):delivery.final_inputs(self.links,self.people,self.status)

class ConfigureSecretsTest(unittest.TestCase):
    def test_platform_workflow_prepares_real_multiline_env_and_secret_bundle(self):
        import yaml,shutil
        from unittest.mock import patch
        workflow=yaml.safe_load((ROOT/'.github/workflows/deploy.yml').read_text(encoding='utf-8'))
        code=next(step['run'] for step in workflow['jobs']['deploy']['steps'] if step.get('shell')=='python')
        names=['RDS_ADMIN_USER','RDS_ADMIN_PASSWORD','OS_DB_PASSWORD','BILLING_DB_PASSWORD','JWT_SECRET','AUTH_SERVICE_TOKEN','OS_SERVICE_TOKEN','BILLING_SERVICE_TOKEN','EXECUTION_SERVICE_TOKEN','OS_RABBIT_PASSWORD','BILLING_RABBIT_PASSWORD','EXECUTION_RABBIT_PASSWORD','RABBIT_ADMIN_PASSWORD','MONGO_ROOT_PASSWORD','MONGO_PASSWORD','NEW_RELIC_LICENSE_KEY']
        env={name:name+'-dummy-value-32-characters-or-more' for name in names};env['RDS_HOST']='sample.private.rds.amazonaws.com'
        if 'SYSTEMROOT' in os.environ:env['SYSTEMROOT']=os.environ['SYSTEMROOT']
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'integracao').mkdir();shutil.copyfile(ROOT/'integracao/configure.py',p/'integracao/configure.py');shutil.copyfile(ROOT/'prepare-secrets.py',p/'prepare-secrets.py')
            output=p/'private/secrets.json'
            code=code.replace("'/tmp/fase4-secrets.json'",repr(str(output)))
            previous=Path.cwd()
            try:
                os.chdir(p)
                with patch.dict(os.environ,env,clear=True):exec(compile(code,'workflow-prepare-secrets','exec'),{})
            finally:os.chdir(previous)
            self.assertGreater(len((p/'integracao/.env').read_text().splitlines()),len(names))
            bundle=json.loads(output.read_text(encoding='utf-8'))
            self.assertIn('os-service-config',[s['metadata']['name'] for s in bundle['items']])
    def test_existing_environment_is_preserved_and_new_auth_secret_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);script=ROOT/'integracao/configure.py';target=p/'configure.py';target.write_bytes(script.read_bytes())
            subprocess.run([sys.executable,str(target)],check=True,capture_output=True)
            first=(p/'.env').read_text(encoding='utf-8');auth=next(line for line in first.splitlines() if line.startswith('AUTH_SERVICE_TOKEN='))
            # Simulate upgrade of an existing environment, preserving every other value.
            old='\n'.join(line for line in first.splitlines() if not line.startswith('AUTH_SERVICE_TOKEN='))+'\n';(p/'.env').write_text(old)
            subprocess.run([sys.executable,str(target)],check=True,capture_output=True)
            second=(p/'.env').read_text(encoding='utf-8');values=dict(line.split('=',1) for line in second.splitlines() if '=' in line)
            self.assertGreaterEqual(len(values['AUTH_SERVICE_TOKEN']),32)
            for line in old.splitlines():
                if '=' in line:self.assertIn(line,second)
            subprocess.run([sys.executable,str(target)],check=True,capture_output=True)
            self.assertEqual(second,(p/'.env').read_text(encoding='utf-8'))
    def test_private_secret_bundle_separates_sql_users_and_does_not_give_lambda_db_access(self):
        names=['RDS_ADMIN_USER','RDS_ADMIN_PASSWORD','OS_DB_PASSWORD','BILLING_DB_PASSWORD','JWT_SECRET','AUTH_SERVICE_TOKEN','OS_SERVICE_TOKEN','BILLING_SERVICE_TOKEN','EXECUTION_SERVICE_TOKEN','OS_RABBIT_PASSWORD','BILLING_RABBIT_PASSWORD','EXECUTION_RABBIT_PASSWORD','RABBIT_ADMIN_PASSWORD','MONGO_ROOT_PASSWORD','MONGO_PASSWORD','NEW_RELIC_LICENSE_KEY']
        values={key:key+'-test-value-with-sufficient-length' for key in names};values['RDS_HOST']='sample.private.rds.amazonaws.com'
        docs=secrets_module.build(values,'{}','test-key');by_name={d['metadata']['name']:d['stringData'] for d in docs}
        self.assertEqual('os_fase4',by_name['os-service-config']['DB_USER']);self.assertEqual('billing_fase4',by_name['billing-service-config']['DB_USER'])
        self.assertNotEqual(by_name['os-service-config']['DB_PASSWORD'],by_name['billing-service-config']['DB_PASSWORD'])
        self.assertEqual(values['AUTH_SERVICE_TOKEN'],by_name['os-service-config']['AUTH_SERVICE_TOKEN'])
        with self.assertRaises(ValueError):secrets_module.build(dict(values,BILLING_DB_PASSWORD=values['OS_DB_PASSWORD']),'{}','key')

class EdgeConfigTest(unittest.TestCase):
    """The edge nginx runs with a read-only root and resolves backends through a variable proxy_pass."""
    def config(self):
        import yaml
        return yaml.safe_load((ROOT/'k8s/overlays/academy/edge-config.yaml').read_text(encoding='utf-8'))['data']['nginx.conf']
    def test_every_backend_is_a_cluster_fqdn(self):
        # nginx 'resolver' ignores resolv.conf search domains, so short Service names fail with 502.
        backends=set(re.findall(r'set \$backend ([^;]+);',self.config()))
        self.assertTrue(backends)
        for backend in backends:
            self.assertRegex(backend,r'^[a-z-]+\.workshop\.svc\.cluster\.local:8080$')
    def test_all_nginx_temp_paths_are_on_writable_tmp(self):
        config=self.config()
        for kind in ['client_body','proxy','fastcgi','uwsgi','scgi']:
            self.assertRegex(config,kind+r'_temp_path /tmp/')
        self.assertIn('pid /tmp/',config)
