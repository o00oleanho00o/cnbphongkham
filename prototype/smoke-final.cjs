const { chromium } = require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const shots = process.env.PEMA_EVIDENCE_DIR ? path.resolve(process.env.PEMA_EVIDENCE_DIR) : path.join(root, 'demo-assets', 'screenshots', 'final'); fs.mkdirSync(shots, { recursive: true });
const tinyPng = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
fs.writeFileSync(path.join(__dirname, 'demo-update.png'), tinyPng);
const results = { startedAt: new Date().toISOString(), checks: [], consoleErrors: [], pageErrors: [], screenshots: [] };
function ok(name, pass, detail='') { results.checks.push({ name, pass: !!pass, detail }); if (!pass) throw new Error(name + (detail ? ': ' + detail : '')); }
async function shot(page, name) { const p=path.join(shots, name+'.png'); await page.screenshot({path:p, fullPage:true}); results.screenshots.push(p); }
(async()=>{
 const browser=await chromium.launch({headless:true}); const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
 const clinic=await ctx.newPage(); clinic.on('console',m=>{if(m.type()==='error')results.consoleErrors.push(m.text())}); clinic.on('pageerror',e=>results.pageErrors.push(e.message));
 await clinic.goto('http://127.0.0.1:4173/clinic-web/'); await clinic.evaluate(()=>localStorage.clear()); await clinic.reload();
 await clinic.getByRole('heading',{name:'Chào buổi sáng, BS. Tâm'}).waitFor();
 ok('36 synthetic patients rendered', (await clinic.locator('.table tbody tr').count())>=5, 'dashboard sample rows visible');
 ok('dynamic dashboard KPI', await clinic.locator('.metric-card').first().locator('.metric-value').innerText().then(x=>x.trim()==='31'));
 await shot(clinic,'clinic-dashboard');
 await clinic.locator('[data-nav="today"]').first().click(); await clinic.getByRole('heading',{name:'Hôm nay tại Pema'}).waitFor();
 const checkin=clinic.getByRole('button',{name:'Check-in'}).first(); ok('reception check-in action visible',await checkin.count()>0); await checkin.click(); await clinic.getByText('Đã cập nhật hàng đợi').waitFor(); ok('reception check-in updates state',await clinic.locator('text=Đã đến').count()>0); await shot(clinic,'clinic-today');
 await clinic.locator('[data-nav="patients"]').first().click(); await clinic.getByPlaceholder(/Nguyễn Minh Linh/).fill('P001'); await clinic.getByRole('button',{name:'Mở →'}).click(); await clinic.getByRole('heading',{name:'Nguyễn Minh Linh'}).waitFor(); await shot(clinic,'clinic-patient-360');
 await clinic.getByRole('button',{name:'Buổi điều trị',exact:true}).click(); await clinic.locator('#session-note').fill('Da ổn hơn sau lần trước; đỏ giảm sau 2 ngày.'); await clinic.locator('#session-aftercare').fill('Giữ SPF 50+ mỗi sáng và dưỡng ẩm theo hướng dẫn đã duyệt.'); await clinic.getByRole('button',{name:'Lưu buổi điều trị'}).click(); await clinic.getByText('Đã lưu buổi điều trị').waitFor(); ok('treatment session save',await clinic.getByRole('heading',{name:'Nguyễn Minh Linh'}).count()>0); ok('session creates aftercare event',await clinic.getByText('Đã gửi hướng dẫn sau buổi').count()>0);
 await clinic.locator('[data-nav="followups"]').first().click(); await clinic.getByRole('heading',{name:'Follow-up Inbox'}).waitFor(); await shot(clinic,'clinic-followup-inbox');
 const firstOpen=clinic.getByRole('button',{name:'Mở'}).first(); await firstOpen.click(); await clinic.getByRole('button',{name:/Duyệt, phản hồi/}).waitFor(); await clinic.locator('#review-reply').fill('Bác sĩ đã xem cập nhật; tiếp tục theo hướng dẫn và báo lại nếu khó chịu tăng.'); await clinic.getByRole('button',{name:/Duyệt, phản hồi/}).click(); await clinic.getByText('Đã gửi phản hồi').waitFor(); ok('follow-up review sends response',true);
 await clinic.locator('[data-nav="ask"]').first().click(); await clinic.getByRole('heading',{name:'Ask Pema'}).first().waitFor(); await clinic.locator('#ask-input').fill('Ai có ảnh gửi sau laser đang chờ xem?'); await clinic.getByRole('button',{name:'Hỏi',exact:true}).click(); await clinic.getByText(/ảnh chờ xem/).waitFor(); ok('Ask Pema dynamic result',true); await shot(clinic,'clinic-ask-pema');
 await clinic.locator('[data-nav="patients"]').first().click(); await clinic.getByPlaceholder(/Nguyễn Minh Linh/).fill('P001'); await clinic.getByRole('button',{name:'Mở →'}).click(); await clinic.getByRole('button',{name:'Tư vấn'}).click(); await clinic.locator('#consult-input').fill('Bệnh nhân báo đỏ giảm, cần đối chiếu ảnh mốc trước khi quyết định bước kế tiếp.'); await clinic.getByRole('button',{name:/Tạo bản nháp/}).click(); await clinic.locator('#editable-draft').fill('Bản nháp đã được bác sĩ sửa: đối chiếu ảnh mốc và xác nhận chăm sóc trước buổi tới.'); await clinic.getByRole('button',{name:/Duyệt & lưu/}).click(); await clinic.getByText('Đã duyệt và nối vào Patient 360').waitFor(); ok('AI note requires review and persists approval',true);
 const patient=await ctx.newPage(); patient.on('console',m=>{if(m.type()==='error')results.consoleErrors.push(m.text())}); patient.on('pageerror',e=>results.pageErrors.push(e.message)); await patient.setViewportSize({width:390,height:844}); await patient.goto('http://127.0.0.1:4173/patient-mobile/'); await patient.getByRole('heading',{name:/Hôm nay của bạn/}).waitFor(); await shot(patient,'patient-home');
 await patient.getByRole('button',{name:'Xem hành trình'}).click(); await patient.getByRole('heading',{name:'Hành trình của bạn'}).waitFor(); await shot(patient,'patient-treatment-journey');
 await patient.locator('[data-screen="home"]').first().click(); await patient.getByRole('button',{name:'Xem hướng dẫn'}).click(); await patient.getByRole('heading',{name:'Chăm sóc tại nhà'}).waitFor(); await shot(patient,'patient-aftercare');
 await patient.getByRole('button',{name:'Gửi cập nhật →'}).click(); await patient.getByRole('heading',{name:'Gửi cập nhật cho Pema'}).waitFor(); await patient.locator('#patient-message').fill('Da hơi khô ở hai má từ tối qua, không đau.'); await patient.locator('#patient-photo').setInputFiles(path.join(__dirname,'demo-update.png')); await patient.locator('#patient-file').filter({hasText:'Đã chọn'}).waitFor(); await patient.locator('#patient-consent').check(); await shot(patient,'patient-send-update'); await patient.getByRole('button',{name:'Gửi cho Pema'}).click(); await patient.getByText('Đã gửi cập nhật').waitFor(); ok('patient sends text + image follow-up',true); await shot(patient,'patient-send-update');
 await clinic.reload(); await clinic.locator('[data-nav="followups"]').first().click(); await clinic.getByRole('heading',{name:'Follow-up Inbox'}).waitFor(); ok('clinic receives cross-app follow-up',await clinic.getByText('Da hơi khô ở hai má từ tối qua, không đau.').count()>0);
 const overflows=await patient.evaluate(()=>({width:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})); ok('mobile no horizontal overflow',overflows.width<=overflows.client+2,JSON.stringify(overflows));
 results.finishedAt=new Date().toISOString(); fs.writeFileSync(path.join(shots,'smoke-results.json'),JSON.stringify(results,null,2)); console.log(JSON.stringify(results,null,2)); await browser.close();
})().catch(async e=>{results.failed=e.message;results.finishedAt=new Date().toISOString();fs.writeFileSync(path.join(shots,'smoke-results.json'),JSON.stringify(results,null,2));console.error(JSON.stringify(results,null,2));process.exit(1)});





