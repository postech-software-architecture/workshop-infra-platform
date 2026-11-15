const vm = require('node:vm');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const s = input.scenario;
const actions = [];
let output;
function Mongo(uri) {
  if (!uri.includes('directConnection=true')) throw new Error('Direct connection required');
  this.getDB = name => {
    if (name === 'local') return {getCollection: () => ({findOne: () => s.existing ? {_id:'rs0',members:[{host:'original:27017'}]} : null})};
    if (name === 'admin') return {
      auth: () => true,
      runCommand: command => {
        if (command.replSetGetStatus) {
          if (s.throwStatus) throw {code:s.code};
          return s.code ? {ok:0,code:s.code} : {ok:1};
        }
        if (command.replSetInitiate) {actions.push('init'); return {ok:1};}
        if (command.hello) return {isWritablePrimary:!!s.primary};
        throw new Error('Unexpected command');
      }
    };
    if (name === 'execution') return {
      getUser: () => s.user ? {roles:[{role:'readWrite',db:'execution'}]} : null,
      createUser: () => actions.push('createUser')
    };
    throw new Error('Unexpected database');
  };
}
try {
  vm.runInNewContext(input.script, {Mongo, process:{env:{MONGO_ROOT_PASSWORD:'example-root',MONGO_PASSWORD:'example-app'}},
                                  sleep:()=>{},print:value=>{output=JSON.parse(value);}});
  console.log(JSON.stringify({ok:true,actions,output}));
} catch(e) {console.log(JSON.stringify({ok:false,actions,error:e.message}));}
