const {chromium}=require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.resolve(__dirname,'../demo-assets/screenshots/mobile-crm02');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch();const errors=[],checks=[];try{
 const ctx=await browser.newContext({viewport:{width:1920,height:1020}}),p=await ctx.newPage();ctx.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));p.on('pageerror',e=>errors.push(e.message));
 await p.goto('http://127.0.0.1:4173/finance/?staff=accountant&patient=P037');
 await p.locator('#entry').waitFor({state:'attached'});
 assert(p.url().includes('/clinic-web/'));assert.equal(await p.locator('.sidebar').count(),1);assert.equal(await p.locator('#role').getAttribute('type'),'hidden');
 await p.locator('[data-finance-tab="overview"]').click();await p.locator('.finance-workspace .metric').first().waitFor();
 await p.screenshot({animations:'disabled',path:path.join(out,'finance-clinic-1920.png')});checks.push('legacy URL preserves account/patient and opens one Clinic shell');
 for(const staff of ['doctor-mai','owner-tam','care-maianh','accountant']){
   await p.locator('#staff-account').selectOption(staff);
   if(staff==='care-maianh'){assert.equal(await p.locator('[data-nav="finance"]').count(),0);continue;}
   await p.locator('[data-nav="finance"]').click();await p.locator('[data-finance-tab="overview"]').first().click();await p.locator('.finance-workspace .metric').first().waitFor();
   if(staff==='doctor-mai'){assert.equal(await p.locator('[data-finance-tab="receipts"]').count(),0);assert.equal(await p.locator('#role').inputValue(),'doctor:D1');}
 }
 checks.push('role switching and finance projection/navigation');
 for(const [width,height] of [[1920,1020],[1440,900],[1280,720],[1024,768],[390,844]]){
   await p.setViewportSize({width,height});
   for(const tab of ['overview','work','rates','receipts']){
     await p.locator(`[data-finance-tab="${tab}"]`).first().click();
     assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${tab} overflows ${width}`);
   }
   await p.screenshot({animations:'disabled',path:path.join(out,`finance-${width}.png`)});
 }
 checks.push('20 finance layouts without document overflow');
 const mobile=await ctx.newPage();await mobile.setViewportSize({width:390,height:844});await mobile.goto('http://127.0.0.1:4173/patient-mobile/');
 const before=await mobile.evaluate(()=>Pema.state.selected);
 const cases=await mobile.evaluate(()=>Pema.state.patients.filter(p=>p.crm?.demoGroup).map(p=>({id:p.id,group:p.crm.demoGroup})));
 assert.equal(cases.length,10);
 for(const c of cases){
   await mobile.locator('.mobile-nav [data-screen="profile"]').click();await mobile.locator('#case-group').selectOption(c.group);
   assert.equal(await mobile.locator('.mobile-app').getAttribute('data-patient-id'),c.id);
   assert(await mobile.evaluate(({id,group})=>PemaCRM.queue({patient:id}).some(t=>t.type===group),c));
   await mobile.locator('.mobile-nav [data-screen="home"]').click();await mobile.locator('[data-next-step]').waitFor();
   assert(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await mobile.screenshot({animations:'disabled',path:path.join(out,`mobile-${c.group}.png`)});
 }
 assert.equal(await mobile.evaluate(()=>Pema.state.selected),before);
 checks.push('10 mobile accounts backed by real CSKH rules, staff selection isolated');
 await mobile.locator('.mobile-nav [data-screen="profile"]').click();await mobile.locator('#case-group').selectOption('d3');
 const id=await mobile.locator('.mobile-app').getAttribute('data-patient-id');
 await mobile.evaluate(id=>{Pema.state.crmActivities.push({id:'private',patientId:id,note:'PRIVATE-CSKH-NOTE'});Pema.save();},id);
 await mobile.locator('.mobile-nav [data-screen="home"]').click();await mobile.locator('[data-next-step] button').click();
 await mobile.locator('#patient-message').fill('Cập nhật thử đúng hồ sơ D3');await mobile.locator('[data-action="send-update"]').click();
 assert.equal(await mobile.evaluate(()=>Pema.state.followups[0].patient),id);assert.equal(await mobile.evaluate(()=>Pema.state.followups[0].owner),'BS. Mai');assert(!await mobile.locator('body').innerText().then(t=>t.includes('PRIVATE-CSKH-NOTE')));
 await mobile.reload();assert.equal(await mobile.evaluate(()=>Pema.state.patients.filter(p=>p.crm?.demoGroup).length),10);
 checks.push('patient reply links to correct file, internal notes hidden, migration idempotent');
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({checks,errors},null,2));console.log(checks);
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
