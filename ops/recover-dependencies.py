"""Restore dependency pod priority; preserve PVCs, credentials and database contents."""
import json
import subprocess

PRIORITY = 'workshop-data-dependencies'


def kube(*args):
    return subprocess.check_output(['kubectl', '-n', 'workshop', *args], text=True)


def main():
    for name in ('rabbit', 'mongo'):
        current = json.loads(kube('get', 'statefulset', name, '-o', 'json'))
        if current['spec']['replicas'] != 1 or current['spec']['template']['metadata']['labels'].get('app') != name:
            raise ValueError('Unexpected dependency StatefulSet scope')
        value = {'metadata': {'resourceVersion': current['metadata']['resourceVersion']},
                 'spec': {'template': {'spec': {'priorityClassName': PRIORITY}}}}
        kube('patch', 'statefulset', name, '--type=strategic', '-p', json.dumps(value))
        raw = kube('get', 'pod', name + '-0', '--ignore-not-found', '-o', 'json').strip()
        if raw:
            pod = json.loads(raw)
            owners = pod['metadata'].get('ownerReferences', [])
            if not any(o.get('uid') == current['metadata']['uid'] and o.get('controller') for o in owners):
                raise ValueError('Unexpected dependency pod ownership')
            # A pre-existing Pending pod cannot acquire its template's new priority.
            # Delete only that unscheduled pod; never PVC/PV or data objects.
            if pod['status']['phase'] == 'Pending' and pod['spec'].get('priorityClassName') != PRIORITY:
                kube('delete', 'pod', name + '-0', '--wait=true', '--timeout=90s')
        print('Updated dependency scheduling: ' + name, flush=True)
    for name in ('rabbit', 'mongo'):
        print(kube('rollout', 'status', 'statefulset/' + name, '--timeout=300s'), flush=True)
    for name in ('os-service', 'billing-service', 'execucao-service', 'fase4-edge'):
        print(kube('wait', '--for=condition=Available', 'deployment/' + name, '--timeout=300s'), flush=True)
        print(kube('rollout', 'status', 'deployment/' + name, '--timeout=180s'), flush=True)


if __name__ == '__main__':
    main()
