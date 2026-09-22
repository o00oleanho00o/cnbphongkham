const {chromium}=require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.resolve(__dirname,'../demo-assets/screenshots/mobile-crm02');
(async()=>{const b=await chromium.launch();const errors=[],checks=[];try{
 const p=await b.newPage({viewport:{width:390,height:844}});p.on('pageerror',e=>errors.push(e.message));
 await p.goto('http://127.0.0.1:4173/native-preview/');
 await p.locator('flt-semantics-placeholder').waitFor({state:'attached'});await p.locator('flt-semantics-placeholder').evaluate(e=>e.click());
 await p.getByRole('button',{name:'Clinic',exact:true}).click();await p.getByRole('button',{name:'Mai Anh · CSKH',exact:true}).click();
 await p.getByRole('button',{name:'Lọc nhóm chăm sóc',exact:true}).waitFor();
 for(const [width,height] of [[360,800],[390,844],[430,932],[768,1024]]){
  await p.setViewportSize({width,height});await p.mouse.move(0,0);await p.waitForTimeout(300);
  const rect=await p.getByRole('button',{name:/ÁD Nguyễn Ánh Dương/}).boundingBox();assert(rect.y<440&&rect.x>=0&&rect.x+rect.width<=width+1);
  await p.screenshot({path:path.join(out,`native-care-${width}.png`)});checks.push({width,height,firstPatientY:rect.y});
 }
 await p.setViewportSize({width:390,height:844});await p.getByRole('button',{name:'Lọc nhóm chăm sóc',exact:true}).click();await p.waitForTimeout(250);
 await p.screenshot({path:path.join(out,'native-care-filter.png')});
 await p.getByRole('button',{name:'Ảnh tiến triển · D+3 1',exact:true}).click();
 await p.getByRole('button',{name:/MC Trần Minh Châu/}).waitFor();await p.mouse.move(0,0);await p.waitForTimeout(250);
 await p.screenshot({path:path.join(out,'native-care-d3.png')});
 await p.getByRole('button',{name:/MC Trần Minh Châu/}).click();await p.waitForTimeout(250);
 await p.screenshot({path:path.join(out,'native-care-contact.png')});
 await p.getByRole('textbox',{name:'Kết quả liên hệ / việc cần bàn giao'}).fill('Đã liên hệ đúng hồ sơ D3; ghi chú nội bộ.');
 await p.getByRole('button',{name:'Lưu kết quả liên hệ',exact:true}).click();
 await p.getByRole('button',{name:'Back',exact:true}).click();
 await p.getByRole('button',{name:'1 Đã liên hệ',exact:true}).click();
 await p.getByRole('button',{name:/MC Trần Minh Châu/}).waitFor();
 checks.push({flow:'Lọc D3 → mở đúng P038 → ghi kết quả → Đã liên hệ',pass:true});
 await p.mouse.move(0,0);await p.waitForTimeout(250);await p.screenshot({path:path.join(out,'native-care-contacted.png')});
 console.log(JSON.stringify({checks,errors}));
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'native-review-results.json'),JSON.stringify({checks,errors},null,2));
 }finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1});
