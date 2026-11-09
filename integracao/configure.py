from pathlib import Path
import json, secrets, hashlib, base64
BASE=Path(__file__).resolve().parent
def write(path,data):
    p=BASE/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data,encoding='utf-8')
envfile=BASE/'.env'
if not envfile.exists():
    env={key:secrets.token_hex(24) for key in ['OS_DB_PASSWORD','BILLING_DB_PASSWORD','MONGO_ROOT_PASSWORD','MONGO_PASSWORD','JWT_SECRET','OS_RABBIT_PASSWORD','BILLING_RABBIT_PASSWORD','EXECUTION_RABBIT_PASSWORD','RABBIT_ADMIN_PASSWORD','OS_SERVICE_TOKEN','BILLING_SERVICE_TOKEN','EXECUTION_SERVICE_TOKEN']}
    envfile.write_text('\n'.join(k+'='+v for k,v in env.items())+'\n',encoding='utf-8')
else:env=dict(line.split('=',1) for line in envfile.read_text().splitlines() if '=' in line)
if 'AUTH_SERVICE_TOKEN' not in env:
    env['AUTH_SERVICE_TOKEN']=secrets.token_hex(24)
    with envfile.open('a',encoding='utf-8') as f: f.write('\nAUTH_SERVICE_TOKEN='+env['AUTH_SERVICE_TOKEN']+'\n')
if 'DEMO_PASSWORD' not in env:
    env['DEMO_PASSWORD']=secrets.token_urlsafe(24)
    with envfile.open('a',encoding='utf-8') as f: f.write('\nDEMO_PASSWORD='+env['DEMO_PASSWORD']+'\n')
write('.gitignore','.env\n*.env\n*.env.*\n!*.env.example\ngenerated/\nevidencias/\n')
if not (BASE/'generated/mongo-key').exists():write('generated/mongo-key',base64.b64encode(secrets.token_bytes(512)).decode())
def pw(value):
    salt=secrets.token_bytes(4);return base64.b64encode(salt+hashlib.sha256(salt+value.encode()).digest()).decode()
users=[];permissions=[];exchanges=[];queues=[];bindings=[]
for kind,user in [('OS','os-service'),('BILLING','billing-service'),('EXECUTION','execucao-service')]:
    users.append({'name':user,'password_hash':pw(env[kind+'_RABBIT_PASSWORD']),'hashing_algorithm':'rabbit_password_hashing_sha256','tags':[]})
    exchange='workshop.commands' if kind=='OS' else 'workshop.events'
    permissions.append({'user':user,'vhost':'/','configure':'^$','write':f'^({exchange}|{user}\\.retry)$','read':f'^{user}\\.inbox$'})
    exchanges.extend([{'name':user+'.retry','vhost':'/','type':'direct','durable':True,'auto_delete':False,'internal':False,'arguments':{}},{'name':user+'.dead','vhost':'/','type':'direct','durable':True,'auto_delete':False,'internal':False,'arguments':{}}])
    for suffix,args in [('inbox',{'x-dead-letter-exchange':user+'.dead','x-dead-letter-routing-key':'dead'}),('retry',{'x-dead-letter-exchange':'','x-dead-letter-routing-key':user+'.inbox'}),('dlq',{})]:
        queues.append({'name':user+'.'+suffix,'vhost':'/','durable':True,'auto_delete':False,'arguments':args})
    bindings.extend([{'source':user+'.retry','vhost':'/','destination':user+'.retry','destination_type':'queue','routing_key':'retry','arguments':{}},{'source':user+'.dead','vhost':'/','destination':user+'.dlq','destination_type':'queue','routing_key':'dead','arguments':{}}])
users.append({'name':'local-admin','password_hash':pw(env['RABBIT_ADMIN_PASSWORD']),'hashing_algorithm':'rabbit_password_hashing_sha256','tags':['administrator']})
permissions.append({'user':'local-admin','vhost':'/','configure':'.*','write':'.*','read':'.*'})
for name in ['workshop.commands','workshop.events']:exchanges.append({'name':name,'vhost':'/','type':'topic','durable':True,'auto_delete':False,'internal':False,'arguments':{}})
commands=['execucao.solicitar-diagnostico.v1', 'billing.gerar-orcamento.v1', 'billing.criar-cobranca.v1', 'execucao.enfileirar-reparo.v1', 'execucao.cancelar-trabalho.v1', 'billing.cancelar-cobranca.v1', 'billing.estornar-pagamento.v1', 'billing.cancelar-orcamento.v1']
events=['execucao.diagnostico-admitido.v1', 'execucao.diagnostico-iniciado.v1', 'execucao.diagnostico-concluido.v1', 'billing.orcamento-gerado.v1', 'billing.geracao-orcamento-falhou.v1', 'billing.orcamento-aprovado.v1', 'billing.orcamento-rejeitado.v1', 'billing.pagamento-confirmado.v1', 'billing.pagamento-recusado.v1', 'billing.pagamento-expirado.v1', 'execucao.reparo-enfileirado.v1', 'execucao.enfileiramento-recusado.v1', 'execucao.trabalho-cancelado.v1', 'execucao.cancelamento-recusado.v1', 'billing.cobranca-cancelada.v1', 'billing.pagamento-estornado.v1', 'billing.compensacao-financeira-pendente.v1', 'billing.orcamento-cancelado.v1', 'execucao.reparo-iniciado.v1', 'execucao.reparo-concluido.v1', 'billing.cobranca-nao-criada.v1']
for key in commands:
    bindings.append({'source':'workshop.commands','vhost':'/','destination':('execucao' if key.startswith('execucao.') else 'billing')+'-service.inbox','destination_type':'queue','routing_key':key,'arguments':{}})
for key in events:
    bindings.append({'source':'workshop.events','vhost':'/','destination':'os-service.inbox','destination_type':'queue','routing_key':key,'arguments':{}})
import re
topics=[]
for user,exchange,keys in [('os-service','workshop.commands',commands),('execucao-service','workshop.events',[k for k in events if k.startswith('execucao.')]),('billing-service','workshop.events',[k for k in events if k.startswith('billing.')])]:
    topics.append({'user':user,'vhost':'/','exchange':exchange,'write':'^('+ '|'.join(re.escape(k) for k in keys)+')$','read':'.*'})
write('generated/rabbit-definitions.json',json.dumps({'users':users,'vhosts':[{'name':'/'}],'permissions':permissions,'topic_permissions':topics,'exchanges':exchanges,'queues':queues,'bindings':bindings},indent=2))

print("Local configuration ready; secrets are excluded from Git.")
