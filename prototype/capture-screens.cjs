const { chromium } = require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs'), path = require('path');
const out=path.resolve(__dirname,'../demo-assets/screenshots/final'), dataOut=path.resolve(__dirname,'../demo-assets/demo-data');
fs.mkdirSync(out,{recursive:true});fs.mkdirSync(dataOut,{recursive:true});
(async()=>{
 const b=await chromium.launch({headless:true}),c=await b.newContext({viewport:{width:1440,height:1000}}),p=await c.newPage();const errors=[];
 p.on('pageerror',e=>errors.push(e.message)); await p.goto('http://127.0.0.1:4173/clinic-web/');
 const state=await p.evaluate(()=>JSON.parse(localStorage.getItem('pema-demo-v2')));fs.writeFileSync(path.join(dataOut,'patients-and-events.json'),JSON.stringify(state,null,2));
 async function snap(page,name){await page.locator('.toast').waitFor({state:'hidden'});await page.screenshot({path:path.join(out,name+'.png'),fullPage:true})}
 await p.locator('[data-nav="patients"]').first().click();await p.locator('[data-patient="P001"]').first().click();
 await p.locator('[data-tab="session"]').first().click();await snap(p,'clinic-treatment');
 await p.locator('[data-tab="consult"]').first().click();await snap(p,'clinic-consultation');
 await p.locator('[data-tab="plan"]').first().click();await snap(p,'clinic-treatment-plan');
 await p.locator('[data-tab="photos"]').first().click();await snap(p,'clinic-before-after');
 await p.locator('[data-action="studio-mode"]').click();await p.locator('#comparison-slider').fill('70');await snap(p,'clinic-before-after-slider');
 await p.locator('[data-tab="overview"]').first().click();await p.locator('[data-modal="note"]').first().click();await snap(p,'clinic-ai-brief');
 await p.locator('.modal-close').first().click();
 const m=await c.newPage();await m.setViewportSize({width:390,height:844});m.on('pageerror',e=>errors.push(e.message));await m.goto('http://127.0.0.1:4173/patient-mobile/');
 await m.locator('[data-screen="journey"]').first().click();await m.locator('[data-screen="progress"]').first().click();await snap(m,'patient-before-after');
 await m.locator('[data-screen="send"]').first().click();await snap(m,'patient-send-update');
 await m.locator('[data-screen="appointments"]').first().click();await snap(m,'patient-appointments');
 await m.locator('[data-screen="profile"]').first().click();await m.locator('[data-screen="docs"]').click();await snap(m,'patient-documents');
 await m.locator('[data-screen="profile"]').first().click();await snap(m,'patient-profile');
 const sizes=[];
 for(const width of [360,390,768]){await m.setViewportSize({width,height:844});await m.locator('[data-screen="home"]').first().click();sizes.push(await m.evaluate(()=>({screen:'patient',width:innerWidth,scroll:document.documentElement.scrollWidth})));}
 await p.setViewportSize({width:390,height:844});await p.locator('[data-nav="followups"]').first().click();await snap(p,'clinic-responsive');sizes.push(await p.evaluate(()=>({screen:'clinic',width:innerWidth,scroll:document.documentElement.scrollWidth})));
 fs.writeFileSync(path.join(out,'capture-manifest.json'),JSON.stringify({capturedAt:new Date().toISOString(),errors,sizes,seedPatients:state.patients.length},null,2));console.log(JSON.stringify({errors,sizes,seedPatients:state.patients.length}));await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
