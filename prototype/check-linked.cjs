const {chromium}=require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const b=await chromium.launch({headless:true});
 const c=await b.newContext({viewport:{width:1440,height:1000}});
 const p=await c.newPage();
 const errors=[]; p.on('pageerror',e=>errors.push(e.message));
 await p.goto('http://127.0.0.1:4173/clinic-web/?screen=patients');
 await p.locator('[data-patient="P001"]').first().click(); await p.waitForTimeout(300);
 const tabs={}; for(const tab of ['overview','consult','plan','session','photos']){ if(tab!=='overview') await p.locator(`.tabbar [data-tab="${tab}"]`).click(); await p.waitForTimeout(100); tabs[tab]=await p.evaluate(()=>({count:document.querySelectorAll('[data-linked-workspace]').length,inside:[...document.querySelectorAll('[data-linked-workspace]')].every(x=>document.querySelector('.content').contains(x)),width:document.documentElement.scrollWidth})); }
 await p.locator('.tabbar [data-tab="overview"]').click(); await p.waitForTimeout(100);
 const clinic={page:await p.locator('body').getAttribute('data-page'),linked:await p.locator('[data-linked-workspace]').count(),plans:await p.locator('[data-linked-panel="services"] .linked-plan').count(),rx:await p.locator('[data-linked-panel="prescriptions"] .linked-rx').count(),width:await p.evaluate(()=>document.documentElement.scrollWidth),tabs};
 await p.screenshot({path:'demo-assets/screenshots/linked-patient.png',fullPage:false});
 await p.screenshot({path:'demo-assets/screenshots/linked-patient-full.png',fullPage:true});
 const beforeInvoices=await p.evaluate(()=>JSON.parse(localStorage.getItem('pema-demo-v2')).patients.find(x=>x.id==='P001').invoices.length); await p.locator('[data-care-action="add-service"]').click(); await p.locator('#linked-service-form').evaluate(f=>f.requestSubmit()); await p.waitForTimeout(150); const afterInvoices=await p.evaluate(()=>JSON.parse(localStorage.getItem('pema-demo-v2')).patients.find(x=>x.id==='P001').invoices.length);
 await p.locator('[data-care-action="add-prescription"]').click(); await p.locator('#linked-rx-form').evaluate(f=>f.requestSubmit()); await p.waitForTimeout(150);
 const draftBefore=await p.locator('.rx-status.draft').count(); await p.locator('[data-care-action="approve-prescription"]').first().click(); await p.waitForTimeout(150);
 const approvedAfter=await p.locator('.rx-status.approved').count();
 await p.setViewportSize({width:390,height:844}); await p.goto('http://127.0.0.1:4173/patient-mobile/'); await p.waitForTimeout(200); await p.locator('nav [data-screen="profile"]').click(); await p.waitForTimeout(200);
 const mobile={linked:await p.locator('[data-mobile-linked]').count(),approved:await p.locator('.mobile-rx').count(),width:await p.evaluate(()=>document.documentElement.scrollWidth),viewport:await p.evaluate(()=>innerWidth),rect:await p.locator('[data-mobile-linked]').boundingBox(),contentHeight:await p.locator('#patient-content').evaluate(x=>({client:x.clientHeight,scroll:x.scrollHeight}))};
 await p.screenshot({path:'demo-assets/screenshots/linked-mobile-prescriptions.png',fullPage:true});
 await p.locator('[data-mobile-linked]').scrollIntoViewIfNeeded(); await p.screenshot({path:'demo-assets/screenshots/linked-mobile-prescriptions-view.png',fullPage:false});
 console.log(JSON.stringify({clinic,beforeInvoices,afterInvoices,draftBefore,approvedAfter,mobile,errors},null,2)); await b.close(); if(errors.length||clinic.linked!==1||clinic.plans<1||clinic.rx<1||Object.values(clinic.tabs).some(x=>x.count!==1||!x.inside||x.width>1440)||afterInvoices!==beforeInvoices+1||mobile.linked!==1||mobile.width>mobile.viewport)process.exit(1);
})().catch(e=>{console.error(e);process.exit(1)});
