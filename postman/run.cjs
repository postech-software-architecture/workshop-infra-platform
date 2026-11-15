// npm install --prefix <runtime-directory> newman@6.2.3
// NEWMAN_MODULE=<absolute module directory> node run.cjs collection.json private/environment.json reports/run.json
// Reports deliberately omit request bodies, response bodies, tokens and passwords.
const fs = require('node:fs');
const path = require('node:path');
const newman = require(process.env.NEWMAN_MODULE || 'newman');
const [collectionFile, environmentFile, reportFile] = process.argv.slice(2);
if (!collectionFile || !environmentFile || !reportFile) throw Error('COLLECTION_ENVIRONMENT_REPORT_REQUIRED');
const report={startedAt:new Date().toISOString(),collection:path.basename(collectionFile),requests:[],assertions:[],errors:[]};
const run = newman.run({collection:JSON.parse(fs.readFileSync(collectionFile,'utf8')),environment:JSON.parse(fs.readFileSync(environmentFile,'utf8')),timeoutRequest:20000,timeoutScript:10000,timeout:360000,reporters:[],iterationCount:1}, (error, summary)=>{
  if(error) report.errors.push({kind:'runner',name:error.name});
  if(summary){
    report.stats=summary.run.stats;
    report.failures=summary.run.failures.map(f=>({at:f.at,source:f.source?.name,name:f.error?.name,test:f.error?.test}));
    const environment=summary.environment.toJSON();
    for(const variable of environment.values) if(/token|password|qr_data/.test(variable.key)) variable.type='secret';
    fs.writeFileSync(environmentFile,JSON.stringify(environment,null,2)+'\n',{mode:0o600});
    report.evidence=Object.fromEntries(environment.values.filter(v=>/^(main|cancel|refund)_(os_id|os_number|work_id|budget_id|payment_id|payment_state|provider_order_id|correlation_id|saga_id|stock_before)$|^webhook_configuration_status$/.test(v.key)).map(v=>[v.key,v.value]));
  }
  report.finishedAt=new Date().toISOString();
  report.ok=!error && !!summary && summary.run.failures.length===0;
  fs.mkdirSync(path.dirname(reportFile),{recursive:true});
  fs.writeFileSync(reportFile,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({collection:report.collection,ok:report.ok,requests:report.requests.length,assertions:report.assertions.length,failures:report.failures||[],errors:report.errors,report:reportFile}));
  process.exitCode=report.ok?0:1;
});
run.on('request',(error,args)=>{
  report.requests.push({name:args.item.name,method:args.request.method,status:args.response?.code,ms:args.response?.responseTime,error:error?.code});
});
run.on('assertion',(error,args)=>report.assertions.push({request:args.item.name,test:args.assertion,passed:!error,skipped:args.skipped||false}));
run.on('exception',(error,args)=>report.errors.push({kind:'script',name:args.error?.name||error?.name}));
