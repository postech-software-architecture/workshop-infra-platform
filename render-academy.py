"""Render Academy manifests locally. No apply and no IAM/RDS mutation."""
from pathlib import Path
import argparse,ipaddress,json,socket,subprocess,sys
def main():
 p=argparse.ArgumentParser();p.add_argument('--rds-host',required=True);p.add_argument('--storage-class',required=True);p.add_argument('--output',required=True);p.add_argument('--check-cluster',action='store_true');a=p.parse_args()
 host=a.rds_host
 if not host.endswith('.rds.amazonaws.com') or any(c in host for c in '/:@ \n'):p.error('Provide a bare private RDS hostname')
 ips=sorted({ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host,5432,socket.AF_INET)})
 if not ips or not all(ip.is_private for ip in ips):p.error('Private IPv4 RDS addresses required')
 if a.check_cluster:
  sc=json.loads(subprocess.check_output(['kubectl','get','storageclass',a.storage_class,'-o','json']))
  if not sc.get('provisioner'):p.error('StorageClass has no provisioner')
  controller=json.loads(subprocess.check_output(['kubectl','get','deployment','aws-load-balancer-controller','-n','kube-system','-o','json']))
  if controller.get('status',{}).get('availableReplicas',0)<1:p.error('Existing AWS Load Balancer Controller is not ready')
  if sc['provisioner'] in ('ebs.csi.aws.com','kubernetes.io/aws-ebs'):
   subprocess.run(['kubectl','get','csidriver','ebs.csi.aws.com'],check=True,stdout=subprocess.DEVNULL)
  # Never install addons or IAM roles to satisfy this preflight. The existing cluster must provide them.
  subprocess.run(['aws','sts','get-caller-identity'],check=True,stdout=subprocess.DEVNULL)
 root=Path(__file__).resolve().parent
 data=subprocess.check_output(['kubectl','kustomize',str(root/'k8s/overlays/academy')],text=True,encoding='utf-8')
 # PVC templates do not specify a class in the base; Kubernetes selects the explicitly rendered class.
 import yaml
 docs=list(yaml.safe_load_all(data))
 for d in docs:
  if d and d['kind']=='StatefulSet':
   for claim in d['spec'].get('volumeClaimTemplates',[]):claim['spec']['storageClassName']=a.storage_class
 Path(a.output).write_text(yaml.safe_dump_all(docs,sort_keys=False),encoding='utf-8')
 print('Rendered only; '+str(len(ips))+' private RDS addresses. Check database passwords and application /32 egress before apply.')
if __name__=='__main__':main()
