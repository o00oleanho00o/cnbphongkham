// Export fresh synthetic fixture projections, never browser/customer records.
const fs=require('fs'),path=require('path'),vm=require('vm');
let saved;
const ctx={structuredClone,console,Event:class{},CustomEvent:class{},localStorage:{getItem:()=>saved,setItem:(k,v)=>saved=v},dispatchEvent(){},addEventListener(){}};
ctx.window=ctx;vm.createContext(ctx);
for(const file of ['data','operations-data','crm-data','crm-automation'])vm.runInContext(fs.readFileSync(path.join(__dirname,'shared',file+'.js'),'utf8'),ctx);
ctx.PemaCRM.ensure();
const projection=ctx.Pema.state.patients.map(p=>({id:p.id,name:p.name,doctor:p.doctor,sessions:p.completed,total:p.total,appointment:p.time||'',day:p.next||'',group:p.crm.demoGroup||'',case:p.crm.demoCase||'',tasks:ctx.PemaCRM.queue({patient:p.id}).map(t=>({id:t.id,type:t.type,title:t.reason,status:'open'}))}));
const target=path.join(__dirname,'../flutter-template/assets/patients.json'),content=JSON.stringify(projection,null,2);
if(process.argv.includes('--check')){if(fs.readFileSync(target,'utf8')!==content)throw Error('Native patient bundle is stale; run export-native-patients.cjs');}
else fs.writeFileSync(target,content);
console.log(`${projection.length} synthetic patients; 10 care groups. ${process.argv.includes('--check')?'Verified':'Exported'}.`);
