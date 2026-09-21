const {chromium}=require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
const out=path.resolve(__dirname,'../demo-assets/screenshots/ui-refresh');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true});const results={at:new Date().toISOString(),errors:[],requests:[],screens:[],checks:[]};
 const ctx=await browser.newContext();
 ctx.on('page',p=>{p.on('pageerror',e=>results.errors.push(e.message));p.on('response',r=>{if(r.status()>=400)results.requests.push({url:r.url(),status:r.status()})})});
 const phone=await ctx.newPage();await phone.goto('http://127.0.0.1:4173/patient-mobile/');await phone.evaluate(()=>document.fonts.ready);
 for(const [width,height] of [[360,800],[390,844],[375,667]]){
  await phone.setViewportSize({width,height});
  for(const screen of ['home','journey','appointments','messages','profile','care','send','progress']){
   const trigger=phone.locator(`[data-screen="${screen}"]`).first();
   if(!await trigger.count())await phone.locator('[data-screen="home"]').first().click();
   await phone.locator(`[data-screen="${screen}"]`).first().click();await phone.evaluate(()=>document.fonts.ready);
   await phone.screenshot({path:path.join(out,`phone-${width}-${height}-${screen}.png`)});
   results.screens.push(await phone.evaluate(({width,height,screen})=>{
    const content=document.querySelector('.mobile-content'),nav=document.querySelector('.mobile-nav'),box=content.getBoundingClientRect();
    return {width,height,screen,pageWidth:document.documentElement.scrollWidth,pageHeight:document.documentElement.scrollHeight,contentHeight:content.clientHeight,scrollHeight:content.scrollHeight,navTop:nav.getBoundingClientRect().top,contentBottom:box.bottom,font:getComputedStyle(document.body).fontFamily};
   },{width,height,screen}));
  }
 }
 await phone.setViewportSize({width:390,height:844});await phone.locator('[data-screen="journey"]').first().click();
 const before=await phone.locator('.event-disclosure').count();await phone.locator('.event-disclosure summary').first().click();
 results.checks.push({name:'timeline details open',pass:await phone.locator('.event-disclosure[open]').count()===1});
 await phone.locator('[data-action="more-history"]').click();results.checks.push({name:'history pagination',pass:await phone.locator('.event-disclosure').count()>before});
 const clinic=await ctx.newPage();await clinic.setViewportSize({width:1440,height:1000});await clinic.goto('http://127.0.0.1:4173/clinic-web/');await clinic.evaluate(()=>document.fonts.ready);
 await clinic.screenshot({path:path.join(out,'clinic-dashboard.png'),fullPage:true});
 await clinic.locator('[data-nav="patients"]').first().click();await clinic.locator('[data-patient="P001"]').first().click();await clinic.screenshot({path:path.join(out,'clinic-patient-360.png'),fullPage:true});
 await clinic.locator('[data-modal="note"]').first().click();
 results.checks.push({name:'dialog focused inside',pass:await clinic.evaluate(()=>document.querySelector('.modal').contains(document.activeElement))});
 await clinic.keyboard.press('Escape');results.checks.push({name:'dialog closes with Escape',pass:await clinic.locator('.modal').count()===0});
 for(const [width,height] of [[1024,768],[768,1024],[390,844]]){
  await clinic.setViewportSize({width,height});await clinic.screenshot({path:path.join(out,`clinic-${width}.png`)});
  results.checks.push({name:`clinic ${width} no horizontal overflow`,pass:await clinic.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)});
 }
 results.checks.push({name:'local font loaded',pass:await clinic.evaluate(()=>document.fonts.check('14px "Be Vietnam Pro"') && getComputedStyle(document.body).fontFamily.includes('Be Vietnam Pro'))});
 results.checks.push({name:'phone content and navigation do not overlap',pass:results.screens.every(s=>s.contentBottom<=s.navTop+1)});
 results.checks.push({name:'phone has no document overflow',pass:results.screens.every(s=>s.pageWidth===s.width&&s.pageHeight===s.height)});
 fs.writeFileSync(path.join(out,'review-results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));await browser.close();
 if(results.errors.length||results.requests.length||results.checks.some(x=>!x.pass))process.exit(1);
})().catch(e=>{console.error(e);process.exit(1)});
