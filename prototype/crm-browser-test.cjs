const {chromium}=require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const out=process.env.PEMA_EVIDENCE_DIR||path.resolve(__dirname,'../demo-assets/screenshots/crm01');fs.mkdirSync(out,{recursive:true});
const report={demoClock:'2026-09-20',checks:[],layouts:[],errors:[],screenshots:[]};
(async()=>{
 const browser=await chromium.launch();try{
 const ctx=await browser.newContext({viewport:{width:1920,height:1020}}),p=await ctx.newPage();
 ctx.on('page',page=>page.on('pageerror',e=>report.errors.push(e.message)));p.on('pageerror',e=>report.errors.push(e.message));
 const nav=async name=>p.locator(`[data-nav="${name}"]`).first().click();
 const shot=async(name,page=p)=>{await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(out,name+'.png')});report.screenshots.push(name+'.png');};
 const check=async(name,fn)=>{await fn();report.checks.push({name,pass:true});};
 const profile=async id=>{await nav('patients');await p.locator(`[data-patient="${id}"]`).first().click();};
 const reset=async()=>{await p.evaluate(()=>Pema.reset());await p.reload();};
 await p.goto('http://127.0.0.1:4173/clinic-web/');
 await shot('01-manager-dashboard');await nav('today');await shot('02-reception');await nav('crm');await shot('03-care-queue');
 await check('CRM queue has ten groups and deterministic 46-patient scenarios',async()=>{assert.equal(await p.locator('.crm-groups [data-crm="filter"]').count(),11);assert.equal(await p.evaluate(()=>Pema.state.patients.filter(p=>p.crm.demoCase).length),18);});
 await profile('P027');await p.locator('.tabbar [data-tab="crm"]').click();await shot('04-patient-crm');
 // Flow B: completed session protocol tasks, log/reschedule and timeline.
 await check('Flow B: D+1 task → callback tomorrow → queue decreases and timeline persists',async()=>{
   await nav('crm');await p.locator('[data-crm="filter"][data-id="d1"]').click();
   await p.locator('[data-crm="task"][data-id*="P025"]').click();await p.locator('#crm-note').fill('Khách đang bận; thống nhất gọi lại 10:30 ngày mai.');await p.locator('#crm-next').fill('2026-09-21T10:30');await shot('05-care-workspace');
   const count=await p.evaluate(()=>PemaCRM.metrics().pending);await p.locator('#crm-submit').click();await p.locator('#crm-task-form').waitFor({state:'hidden'});assert.equal(await p.evaluate(()=>PemaCRM.metrics().pending),count-1);
   await profile('P025');await p.locator('[data-tab="history"]').click();assert.match(await p.locator('.crm-timeline').innerText(),/thống nhất gọi lại/);await shot('06-crm-timeline');
 });
 // Flow C: validate conflict, then atomically save task + appointment, mobile sees booking.
 await check('Flow C: dormant customer → booking conflict → corrected booking → task/metrics/mobile',async()=>{
   await nav('crm');await p.locator('[data-crm="filter"][data-id="dormant90"]').click();await p.locator('[data-crm="task"][data-id*="P031"]').click();
   await p.locator('#crm-outcome').selectOption('booked');await p.locator('#crm-note').fill('Khách đồng ý quay lại để bác sĩ xem liệu trình còn lại.');await p.locator('#crm-submit').click();
   assert.equal(await p.locator('#booking-patient').inputValue(),'P031');await shot('07-crm-booking-prefill');
   await p.locator('#booking-date').fill('2026-09-20');await p.locator('#booking-time').fill('08:00');await p.locator('#booking-form button[type="submit"]').click();assert.match(await p.locator('#ops-error').innerText(),/Trùng/);
   assert.equal(await p.evaluate(()=>PemaCRM.metrics().booked),0);await p.locator('#booking-date').fill('2026-09-27');await p.locator('#booking-time').fill('10:00');await p.locator('#booking-form button[type="submit"]').click();await p.locator('#booking-form').waitFor({state:'hidden'});
   assert.equal(await p.evaluate(()=>PemaCRM.metrics().booked),1);assert.equal(await p.evaluate(()=>PemaCRM.profile(Pema.patient('P031')).expectedNextVisitAt),'2026-09-27');assert.equal(await p.evaluate(()=>PemaCRM.metrics().reactivated),0);
   await nav('dashboard');await shot('08-manager-after-booking');
   const mobile=await ctx.newPage();await mobile.setViewportSize({width:390,height:844});await mobile.goto('http://127.0.0.1:4173/patient-mobile/');await mobile.evaluate(()=>localStorage.setItem('pema-patient-identity','P031'));await mobile.reload();await mobile.locator('[data-screen="appointments"]').first().click();assert(await mobile.getByText('27/9/2026 · 10:00',{exact:true}).count());await shot('09-mobile-after-booking',mobile);await mobile.close();
 });
 await check('Flow A: check-in → diagnosis → service/session → draft/approve → payment → mobile',async()=>{
   await reset();await nav('today');await p.locator('[data-crm="arrive"][data-id="A0-0"]').click();await p.locator('[data-crm="start"][data-id="A0-0"]').click();await profile('P001');await p.locator('.tabbar [data-tab="consult"]').click();
   await p.locator('#crm-history').fill('Tiền sử tổng hợp: da nhạy cảm, đã hỏi dị ứng.');await p.locator('#crm-diagnosis').fill('Nhận định mô phỏng do bác sĩ nhập, cần đối chiếu ảnh và thăm khám.');await p.locator('#crm-clinical-form button[type="submit"]').click();assert.equal(await p.evaluate(()=>Pema.patient('P001').clinical.reviewedBy),'BS. Tâm');
   await p.locator('#consult-input').fill('Trao đổi mục tiêu chăm sóc và lần hẹn tiếp theo.');await p.locator('[data-action="generate-note"]').click();await p.locator('[data-action="approve-note"]').click();
   await p.locator('[data-care-action="add-service"]').click();await p.locator('#linked-service-form button[type="submit"]').click();
   await p.locator('.tabbar [data-tab="session"]').click();await p.locator('#session-protocol').selectOption('laser-co2');await p.locator('#session-note').fill('Buổi điều trị giả lập đã hoàn tất, bác sĩ xác nhận trước khi lưu.');await p.locator('#session-aftercare').fill('Hướng dẫn mẫu có bác sĩ duyệt; liên hệ phòng khám nếu cần.');await p.locator('[data-action="save-session"]').click();
   assert.equal(await p.evaluate(()=>Pema.state.operations.appointments.find(a=>a.id==='A0-0').status),'completed');assert.equal(await p.evaluate(()=>Pema.patient('P001').crm.recommendationAt),'2026-10-20');
   await p.locator('[data-care-action="add-prescription"]').click();await p.locator('#quick-product-search').fill('H002');await p.locator('[data-quick-add="H002"]').click();await p.locator('#usage-0').fill('Hướng dẫn dùng giả lập đã được kiểm thử');
   const [review]=await Promise.all([ctx.waitForEvent('page'),p.locator('#quick-save').click()]);await review.waitForLoadState();
   const mobile=await ctx.newPage();await mobile.setViewportSize({width:390,height:844});await mobile.goto('http://127.0.0.1:4173/patient-mobile/');await mobile.evaluate(()=>localStorage.setItem('pema-patient-identity','P001'));await mobile.reload();await mobile.locator('[data-screen="profile"]').first().click();assert.equal(await mobile.locator('[data-mobile-order]').count(),0);
   await review.locator('#approve').click();await review.locator('body[data-approved="true"]').waitFor();await review.close();await mobile.reload();await mobile.locator('[data-screen="profile"]').first().click();await mobile.locator('[data-mobile-order]').waitFor();assert.equal(await mobile.locator('[data-mobile-order]').count(),1);
   await nav('cashier');await p.locator('[data-ops="invoice-filter"][data-value="due"]').click();await p.locator('[data-ops="pay"][data-id="HD-DEMO-001"]').click();await p.locator('[data-ops="save-pay"]').click();assert(await p.evaluate(()=>Pema.patient('P001').invoices.find(i=>i.id==='HD-DEMO-001').paid));
   await mobile.reload();await mobile.locator('[data-screen="profile"]').first().click();await mobile.locator('[data-screen="docs"]').click();assert.match(await mobile.locator('.doc-row').filter({hasText:'HD-DEMO-001'}).innerText(),/Đã thanh toán/);await shot('10-mobile-approved-order',mobile);await mobile.close();
 });
 await check('D+3 patient sends update/photo with consent → clinical inbox',async()=>{
   const mobile=await ctx.newPage();await mobile.setViewportSize({width:390,height:844});await mobile.goto('http://127.0.0.1:4173/patient-mobile/');await mobile.evaluate(()=>localStorage.setItem('pema-patient-identity','P026'));await mobile.reload();await mobile.locator('[data-screen="send"]').first().click();await mobile.locator('#patient-message').fill('Cập nhật D+3 giả lập: gửi ảnh để bác sĩ xem.');
   await mobile.locator('#patient-photo').setInputFiles({name:'synthetic-pixel.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')});await mobile.locator('#patient-consent').check();await mobile.locator('[data-action="send-update"]').click();await mobile.getByText('Đã gửi cập nhật').waitFor();await nav('followups');assert(await p.getByText('Cập nhật D+3 giả lập: gửi ảnh để bác sĩ xem.').count());await shot('11-d3-clinical-inbox');await mobile.close();
 });
 // Responsive includes workspace forms and new Patient 360 tabs.
 for(const [width,height]of[[1920,1020],[1440,900],[1280,720],[1024,768],[390,844]]) {
   await p.setViewportSize({width,height});
   for(const screen of ['dashboard','today','crm']){await nav(screen);const size=await p.evaluate(()=>document.documentElement.scrollWidth);report.layouts.push({screen,width,height,scrollWidth:size,pass:size<=width});assert(size<=width,screen+' '+width);if(screen==='crm')await shot('queue-'+width);}
   await profile('P027');for(const tab of ['crm','history','finance']){await p.locator(`.tabbar [data-tab="${tab}"]`).click();const size=await p.evaluate(()=>document.documentElement.scrollWidth);report.layouts.push({screen:'patient-'+tab,width,height,scrollWidth:size,pass:size<=width});assert(size<=width);}
   await nav('crm');await p.locator('[data-crm="filter"][data-id="d1"]').click();await p.locator('[data-crm="task"]').first().click();const size=await p.evaluate(()=>document.documentElement.scrollWidth);report.layouts.push({screen:'workspace',width,height,scrollWidth:size,pass:size<=width});assert(size<=width);if(width===390)await shot('workspace-390');await p.locator('.modal-close').click();
 }
 await check('200-appointment rendering: bounded table, search, pagination and no overflow',async()=>{
   await p.setViewportSize({width:1920,height:1020});await p.evaluate(()=>{const o=PemaOps.seed(),base=o.appointments.filter(a=>a.date===PemaCRM.DAY);o.appointments=o.appointments.filter(a=>a.date!==PemaCRM.DAY).concat(Array.from({length:200},(_,i)=>({...base[i%base.length],id:'STRESS-'+i,note:'Isolated UI load fixture, not a clinically valid resource schedule'})));Pema.save();});await nav('today');
   assert.equal(await p.locator('.crm-reception-table tbody tr').count(),25);assert.match(await p.locator('.invoice-pagination').innerText(),/200 lịch/);await p.locator('[data-crm="today-page"][data-id="1"]').click();assert.match(await p.locator('.invoice-pagination').innerText(),/Trang 2\/8/);assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await shot('12-reception-200-row-load');
   await p.locator('#crm-today-search').fill('P001');await p.locator('#crm-today-search').dispatchEvent('change');assert(await p.locator('.crm-reception-table tbody tr').count()<25);await reset();
 });
 await check('separate staff accounts: care, doctor, accountant and owner workspaces',async()=>{
   await p.locator('#staff-account').selectOption('care-maianh');assert.equal(await p.locator('body').getAttribute('data-page'),'crm');assert.equal(await p.locator('[data-nav="dashboard"]').count(),0);assert.equal(await p.locator('[data-nav="cashier"]').count(),0);assert.equal(await p.locator('a[href*="../finance/"]').count(),0);await shot('13-cskh-account');
   const denied=await p.evaluate(()=>{try{PemaCRM.clinical('P001',{history:'test',diagnosis:'test'});return false;}catch(e){return true;}});assert(denied);
   await p.locator('#staff-account').selectOption('doctor-mai');assert.match(await p.locator('h1').innerText(),/Không gian bác sĩ/);assert.equal(await p.locator('[data-nav="crm"]').count(),0);assert.equal(await p.locator('[data-nav="cashier"]').count(),0);assert.equal(await p.getByText('Phát sinh hôm nay',{exact:true}).count(),0);await shot('14-doctor-account');
   await nav('patients');const ids=await p.locator('.table tbody tr[data-patient]').evaluateAll(rows=>rows.map(x=>x.dataset.patient));assert(await p.evaluate(ids=>ids.every(id=>PemaStaff.owns(Pema.patient(id))),ids));
   const deniedPay=await p.evaluate(()=>{try{PemaOps.pay('P002','HD-DEMO-002',1000,'Tiền mặt');return false;}catch(e){return true;}});assert(deniedPay);
   await p.locator('#staff-account').selectOption('accountant');assert.equal(await p.locator('body').getAttribute('data-page'),'cashier');assert.equal(await p.locator('[data-nav="crm"]').count(),0);await shot('15-accountant-account');
   await p.locator('#staff-account').selectOption('owner-tam');assert.equal(await p.locator('body').getAttribute('data-page'),'dashboard');assert.equal(await p.locator('[data-nav="crm"]').count(),1);
 });
 assert.equal(report.errors.length,0);
 }finally{await browser.close();}
 fs.writeFileSync(path.join(out,'crm-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({checks:report.checks.length,layouts:report.layouts.length,errors:report.errors}));
})().catch(e=>{report.failed=e.stack;fs.writeFileSync(path.join(out,'crm-results.json'),JSON.stringify(report,null,2));console.error(e);process.exitCode=1;});
