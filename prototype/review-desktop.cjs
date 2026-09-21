const {chromium}=require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
const out=path.resolve(__dirname,'../demo-assets/screenshots/desktop-1920');
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage();
 const report={at:new Date().toISOString(),errors:[],screens:[]};
 page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto('http://127.0.0.1:4173/clinic-web/');
 async function capture(name,width,height){
  await page.evaluate(()=>document.fonts.ready);
  const metrics=await page.evaluate(()=>({pageWidth:document.documentElement.scrollWidth,contentWidth:document.querySelector('.content').clientWidth,contentRight:document.querySelector('.content').getBoundingClientRect().right}));
  report.screens.push({name,width,height,...metrics,pass:metrics.pageWidth<=width});
  await page.screenshot({path:path.join(out,`${width}-${name}.png`)});
 }
 for(const [width,height] of [[1920,1020],[1440,900],[1280,720],[1024,768],[390,844]]){
  await page.setViewportSize({width,height});
  for(const name of ['dashboard','today','schedule','patients','followups','studio','resources','services','cashier','ask','guide']){
   await page.locator(`[data-nav="${name}"]`).first().click();
   await capture(name,width,height);
  }
  await page.locator('[data-nav="patients"]').first().click();
  await page.locator('[data-patient="P001"]').first().click();
  for(const tab of ['overview','consult','plan','session','photos']){
   await page.locator(`[data-tab="${tab}"]`).first().click();
   await capture(`patient-${tab}`,width,height);
  }
 }
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({screens:report.screens.length,failures:report.screens.filter(x=>!x.pass),errors:report.errors},null,2));
 await browser.close();
 if(report.errors.length||report.screens.some(x=>!x.pass))process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
