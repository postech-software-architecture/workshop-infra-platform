// Exports only the existing synthetic demo-user password, encrypted for the requester.
// No JWT signing keys, database credentials or provider credentials are exported.
const fs = require('node:fs');
const crypto = require('node:crypto');
const cp = require('node:child_process');
const publicKey = crypto.createPublicKey(process.env.RECIPIENT_PUBLIC_KEY);
if (publicKey.asymmetricKeyType !== 'rsa' || publicKey.asymmetricKeyDetails.modulusLength < 3072) throw Error('RSA_3072_REQUIRED');
const password = cp.execFileSync('kubectl', ['-n','workshop','get','secret','fase4-demo-credentials','-o','jsonpath={.data.DEMO_PASSWORD}'], {encoding:'utf8'});
if (!password.trim()) throw Error('EXISTING_DEMO_PASSWORD_NOT_FOUND');
const env = JSON.parse(fs.readFileSync('postman/SOAT4.template.postman_environment.json','utf8'));
env.values.find(v=>v.key==='demo_password').value = Buffer.from(password,'base64').toString('utf8');
env.name = 'SOAT4 - PRIVADO - usuarios de demonstracao';
const key = crypto.randomBytes(32), iv = crypto.randomBytes(12);
const cipher = crypto.createCipheriv('aes-256-gcm',key,iv);
const ciphertext = Buffer.concat([cipher.update(JSON.stringify(env),'utf8'),cipher.final()]);
const wrappedKey = crypto.publicEncrypt({key:publicKey,oaepHash:'sha256',padding:crypto.constants.RSA_PKCS1_OAEP_PADDING},key);
fs.mkdirSync('encrypted-export',{recursive:true});
fs.writeFileSync('encrypted-export/demo-environment.encrypted.json',JSON.stringify({format:'rsa-oaep-sha256+aes-256-gcm-v1',wrappedKey:wrappedKey.toString('base64'),iv:iv.toString('base64'),tag:cipher.getAuthTag().toString('base64'),ciphertext:ciphertext.toString('base64')}));
console.log('Demo environment encrypted for the supplied recipient; no plaintext artifact.');
