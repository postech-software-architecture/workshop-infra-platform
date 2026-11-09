import os, json, base64, urllib.request
from pathlib import Path
credentials=base64.b64encode(('local-admin:'+os.environ['RABBIT_ADMIN_PASSWORD']).encode()).decode()
request=urllib.request.Request('http://rabbit:15672/api/definitions',data=Path('/definitions.json').read_bytes(),headers={'Authorization':'Basic '+credentials,'Content-Type':'application/json'},method='POST')
with urllib.request.urlopen(request,timeout=30) as response: print('Broker definitions configured:',response.status)
