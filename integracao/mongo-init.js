const c=new Mongo('mongodb://mongo:27017');
const admin=c.getDB('admin');
admin.auth('root',process.env.MONGO_ROOT_PASSWORD);
try { admin.runCommand({replSetGetStatus:1}); } catch(e) { if(e.code===94)admin.runCommand({replSetInitiate:{_id:'rs0',members:[{_id:0,host:'mongo:27017'}]}});else throw e; }
let primary=false;
for(let i=0;i<60;i++){if(admin.runCommand({hello:1}).isWritablePrimary){primary=true;break;}sleep(500);}
if(!primary)throw new Error('No primary');
const db=c.getDB('execution');
if(!db.getUser('execution'))db.createUser({user:'execution',pwd:process.env.MONGO_PASSWORD,roles:[{role:'readWrite',db:'execution'}]});
