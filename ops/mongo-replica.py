"""Inspect or complete an absent Mongo replica configuration; never force/reconfigure."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSPECT = "const c=new Mongo('mongodb://127.0.0.1:27017/?directConnection=true&serverSelectionTimeoutMS=5000'); const a=c.getDB('admin'); a.auth('root',process.env.MONGO_ROOT_PASSWORD||process.env.MONGO_INITDB_ROOT_PASSWORD); let s; try{s=a.runCommand({replSetGetStatus:1})}catch(e){s={ok:0,code:e.code,codeName:e.codeName}}; const h=a.runCommand({hello:1}); const cfg=c.getDB('local').getCollection('system.replset').findOne(); print(JSON.stringify({primary:h.isWritablePrimary===true,setName:h.setName,statusCode:s.code||0,statusOk:s.ok,configurationPresent:!!cfg,members:cfg?cfg.members.map(m=>m.host):[]}));"


def kube(*args, input=None):
    p = subprocess.run(['kubectl', '-n', 'workshop', *args], input=input,
                       capture_output=True, text=True, timeout=360)
    if p.returncode:
        raise RuntimeError('Kubernetes operation failed: ' + args[0] + '; private output suppressed')
    return p.stdout


def execute(script):
    wrapped = 'try {\n' + script + '\n} catch(e) { print(JSON.stringify({operationError:true,code:e.code||0,name:e.name||"Error"})); }'
    output = kube('exec', 'mongo-0', '--', 'mongosh', '--nodb', '--quiet', '--eval', wrapped)
    for line in reversed(output.splitlines()):
        if line.startswith('{'):
            result = json.loads(line)
            if result.get('operationError'):
                print(json.dumps(result), flush=True)
                raise ValueError('Mongo operation failed with code ' + str(result['code']))
            return result
    raise ValueError('No structured Mongo result; private output suppressed')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--operation', choices=('inspect', 'bootstrap'), default='inspect')
    operation = p.parse_args().operation
    before = execute(INSPECT)
    print(json.dumps({'before': before}), flush=True)
    if operation == 'inspect':
        return
    if not before['primary'] and (before['statusCode'] != 94 or before['configurationPresent']):
        raise ValueError('Only absent replica configuration may be initialized; no force/reconfiguration allowed')
    docs = list(yaml.safe_load_all(kube('kustomize', str(ROOT / 'k8s/overlays/academy'))))
    selected = [d for d in docs if (d['kind'], d['metadata']['name']) in
                (('ConfigMap', 'mongo-bootstrap'), ('Service', 'mongo'))]
    if len(selected) != 2:
        raise ValueError('Unexpected manifest scope')
    kube('apply', '--dry-run=server', '-f', '-', input=yaml.safe_dump_all(selected))
    kube('apply', '-f', '-', input=yaml.safe_dump_all(selected))
    script = next(d for d in selected if d['kind'] == 'ConfigMap')['data']['init.js']
    print(json.dumps({'bootstrap': execute(script)}), flush=True)
    after = execute(INSPECT)
    if not after['primary']:
        raise ValueError('Writable primary not confirmed')
    print(json.dumps({'after': after}), flush=True)
    sts = next(d for d in docs if d['kind'] == 'StatefulSet' and d['metadata']['name'] == 'mongo')
    probe = sts['spec']['template']['spec']['containers'][0]['readinessProbe']
    patch = [{'op': 'replace', 'path': '/spec/template/spec/containers/0/readinessProbe', 'value': probe}]
    kube('patch', 'statefulset', 'mongo', '--type=json', '-p', json.dumps(patch))
    print(kube('rollout', 'status', 'statefulset/mongo', '--timeout=300s'), flush=True)
    kube('rollout', 'restart', 'deployment/execucao-service')
    print(kube('rollout', 'status', 'deployment/execucao-service', '--timeout=300s'), flush=True)
    print(kube('get', 'deployments,statefulsets,pvc', '-o', 'wide'), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('Mongo operation failed: ' + (str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
