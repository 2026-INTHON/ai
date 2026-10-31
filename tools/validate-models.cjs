const fs=require('node:fs'),path=require('node:path'),validator=require('gltf-validator');
const root=path.resolve(process.argv[2]||path.join(__dirname,'../assets/models'));
(async()=>{
 const summaries=[];
 for(const key of ['girlfriend','friend','manager','professor']){
  const bytes=fs.readFileSync(path.join(root,key,key+'.glb'));
  const report=await validator.validateBytes(new Uint8Array(bytes),{uri:key+'.glb',maxIssues:200});
  summaries.push({id:key,errors:report.issues.numErrors,warnings:report.issues.numWarnings,messages:report.issues.messages.filter(m=>m.severity<2).slice(0,8)});
 }
 fs.writeFileSync(path.join(root,'validation.json'),JSON.stringify(summaries,null,2));
 console.log(JSON.stringify(summaries));
 if(summaries.some(item=>item.errors||item.warnings))process.exitCode=1;
})();
