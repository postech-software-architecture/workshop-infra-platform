"""Render private Kubernetes Secrets from local environment. Never apply or print values."""
from pathlib import Path
import argparse,json,os

def build(values,definitions,keyfile):
    required=['RDS_HOST','RDS_ADMIN_USER','RDS_ADMIN_PASSWORD','OS_DB_PASSWORD','BILLING_DB_PASSWORD','JWT_SECRET','AUTH_SERVICE_TOKEN','OS_SERVICE_TOKEN','BILLING_SERVICE_TOKEN','EXECUTION_SERVICE_TOKEN','OS_RABBIT_PASSWORD','BILLING_RABBIT_PASSWORD','EXECUTION_RABBIT_PASSWORD','RABBIT_ADMIN_PASSWORD','MONGO_ROOT_PASSWORD','MONGO_PASSWORD','NEW_RELIC_LICENSE_KEY']
    missing=[name for name in required if not values.get(name)]
    if missing:raise ValueError('Missing environment names: '+', '.join(missing))
    if values['OS_DB_PASSWORD']==values['BILLING_DB_PASSWORD']:raise ValueError('Distinct SQL application credentials required')
    if len(values['AUTH_SERVICE_TOKEN'])<32:raise ValueError('AUTH_SERVICE_TOKEN too short')
    host=values['RDS_HOST']
    if not host.endswith('.rds.amazonaws.com') or any(c in host for c in '/:@ \n'):raise ValueError('Bare private RDS hostname required')
    def secret(name,data):return {'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':'workshop'},'type':'Opaque','stringData':data}
    docs=[secret('fase4-rds-bootstrap',{'PGHOST':host,'PGPORT':'5432','PGDATABASE':'postgres','PGUSER':values['RDS_ADMIN_USER'],'PGPASSWORD':values['RDS_ADMIN_PASSWORD'],'OS_APP_PASSWORD':values['OS_DB_PASSWORD'],'BILLING_APP_PASSWORD':values['BILLING_DB_PASSWORD']}),
          secret('mongo-secrets',{'MONGO_INITDB_ROOT_USERNAME':'root','MONGO_INITDB_ROOT_PASSWORD':values['MONGO_ROOT_PASSWORD'],'MONGO_ROOT_PASSWORD':values['MONGO_ROOT_PASSWORD'],'MONGO_PASSWORD':values['MONGO_PASSWORD']}),
          secret('mongo-key',{'keyfile':keyfile}),secret('rabbit-secrets',{'RABBITMQ_DEFAULT_USER':'local-admin','RABBITMQ_DEFAULT_PASS':values['RABBIT_ADMIN_PASSWORD'],'RABBIT_ADMIN_PASSWORD':values['RABBIT_ADMIN_PASSWORD']}),
          secret('broker-definitions',{'definitions.json':definitions}),secret('newrelic-otel',{'NEW_RELIC_LICENSE_KEY':values['NEW_RELIC_LICENSE_KEY'],'NEW_RELIC_OPENTELEMETRY_ENDPOINT':values.get('NEW_RELIC_OPENTELEMETRY_ENDPOINT','https://otlp.nr-data.net')})]
    for kind,runtime in [('OS','os-service'),('BILLING','billing-service'),('EXECUTION','execucao-service')]:
        data={'JWT_SECRET':values['JWT_SECRET'],'SERVICE_TOKEN':values[kind+'_SERVICE_TOKEN'],'RABBIT_PASSWORD':values[kind+'_RABBIT_PASSWORD']}
        if kind!='EXECUTION':
            user=kind.lower()+'_fase4'
            data.update(DB_URL='jdbc:postgresql://'+host+':5432/'+user+'?sslmode=require',DB_USER=user,DB_PASSWORD=values[kind+'_DB_PASSWORD'])
        else:
            from urllib.parse import quote
            data['MONGO_URI']='mongodb://execution:'+quote(values['MONGO_PASSWORD'],safe='')+'@mongo:27017/execution?replicaSet=rs0&authSource=execution'
        if kind=='OS':data.update(AUTH_SERVICE_TOKEN=values['AUTH_SERVICE_TOKEN'],BILLING_SERVICE_TOKEN=values['BILLING_SERVICE_TOKEN'],EXECUTION_SERVICE_TOKEN=values['EXECUTION_SERVICE_TOKEN'])
        if kind=='BILLING':
            for name in ['MP_ACCESS_TOKEN','MP_SELLER_ID','MP_APPLICATION_ID','MP_POS_ID','MP_WEBHOOK_SECRET','MAIL_HOST','MAIL_PORT','MAIL_USERNAME','MAIL_PASSWORD','MAIL_FROM']:
                if values.get(name):data[name]=values[name]
        docs.append(secret(runtime+'-config',data))
    return docs

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--definitions',type=Path,required=True);p.add_argument('--keyfile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    docs=build(dict(os.environ),a.definitions.read_text(),a.keyfile.read_text())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    # Avoid a world-readable intermediate file; the caller owns the directory on Windows.
    descriptor=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as f:json.dump({'apiVersion':'v1','kind':'List','items':docs},f)
    print('Private Secret file rendered; no credentials printed and no resources applied.')
if __name__=='__main__':main()
