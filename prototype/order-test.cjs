const {chromium} = require('C:/Users/email/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict'), fs = require('fs'), path = require('path');
const out = process.env.PEMA_EVIDENCE_DIR || path.resolve(__dirname, '../demo-assets/screenshots/orders');
fs.mkdirSync(out, {recursive:true});
const report = {checks:[], errors:[]};
const base = 'http://127.0.0.1:4173';
(async () => {
  const browser = await chromium.launch();
  try {
    const ctx = await browser.newContext({viewport:{width:1440,height:900}});
    ctx.on('page', p => p.on('pageerror', e => report.errors.push(e.message)));
    const p = await ctx.newPage();
    const check = async (name, fn) => { await fn(); report.checks.push(name); console.log('PASS', name); };
    await p.goto(base + '/clinic-web/?screen=cashier');
    await check('Catalog parity, missing types and accent-insensitive search', async () => {
      assert.deepEqual(await p.evaluate(() => PemaProducts.counts), {totalRows:115,prescription:30,consultation:78,unresolved:7});
      assert.equal(await p.evaluate(() => PemaProducts.get('H095').outputType), 'UNRESOLVED');
    });
    await p.locator('[data-ops="quick-order"]').first().click();
    await check('Empty order rejected, no partial invoice', async () => {
      const n = await p.evaluate(() => Pema.patient('P001').invoices.length);
      await p.locator('#quick-save').click();
      assert.match(await p.locator('#quick-error').textContent(), /ít nhất/);
      assert.equal(await p.evaluate(() => Pema.patient('P001').invoices.length), n);
    });
    async function add(code) { await p.locator('#quick-product-search').fill(code); await p.locator(`[data-quick-add="${code}"]`).click(); }
    await add('H002'); await add('H005'); await add('H006'); await add('H095');
    await p.locator('#qty-0').fill('3');
    for(let i=0;i<4;i++) await p.locator(`#usage-${i}`).fill(`Hướng dẫn thử nghiệm ${i+1}\nTần suất và thời gian theo bác sĩ.`);
    await p.locator('#line-note-1').fill('Ghi chú riêng được giữ lại');
    await p.locator('#quick-note').fill('Dặn dò tổng hợp thử nghiệm');
    await p.locator('#quick-diagnosis').fill('Nội dung tư vấn tổng hợp');
    await check('Editor responsive at five target viewports and no field loss', async () => {
      for(const [width,height] of [[1920,1020],[1440,900],[1280,720],[1024,768],[390,844]]) {
        await p.setViewportSize({width,height});
        assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `overflow ${width}`);
        await p.screenshot({path:path.join(out,`editor-${width}.png`)});
      }
      await p.setViewportSize({width:1440,height:900});
      assert.equal(await p.locator('#qty-0').inputValue(), '3');
    });
    let review;
    await check('Mixed order persists every line, price snapshot and draft review', async () => {
      [review] = await Promise.all([ctx.waitForEvent('page'), p.locator('#quick-save').click()]);
      await review.waitForLoadState();
      assert.equal(await review.locator('.print-item').count(), 3);
      assert.match(await review.locator('#review-excluded').textContent(), /Cần phân loại 1/);
      assert.equal(await review.locator('#approve').isDisabled(), true);
      const o = await p.evaluate(() => Pema.patient('P001').quickOrders[0]);
      assert.equal(o.items.length,4); assert.equal(o.items[0].quantity,3); assert.equal(o.items[0].unitPrice,5500);
      assert.equal(o.items[1].note,'Ghi chú riêng được giữ lại');
      const total = o.items.reduce((s,x)=>s+x.quantity*x.unitPrice,0);
      assert.equal(await p.evaluate(id=>Pema.patient('P001').invoices.find(x=>x.id===id).amount,o.invoiceId),total);
      assert.match(await review.title(), /Tách đơn – /);
    });
    const orderId = await p.evaluate(() => Pema.patient('P001').quickOrders[0].id);
    const mobile = await ctx.newPage(); await mobile.goto(base + '/patient-mobile/');
    await check('Draft absent from mobile and direct print blocked', async () => {
      assert.equal(await mobile.locator('[data-mobile-order]').count(),0);
      await review.pdf({path:path.join(out,'draft.pdf'),preferCSSPageSize:true});
      assert.equal(await review.locator('[data-print="all"]').isDisabled(),true);
    });
    await check('Reopen draft, require route reason, retain all other fields', async () => {
      await p.reload();
      await p.locator(`[data-order-edit="${orderId}"]`).click();
      assert.equal(await p.locator('#qty-0').inputValue(),'3');
      await p.locator('#route-3').selectOption('CONSULTATION');
      await p.locator('#quick-save').click();
      assert.match(await p.locator('#quick-error').textContent(), /lý do/);
      await p.locator('#reason-3').fill('Phân loại thủ công phục vụ kiểm thử');
      const [next] = await Promise.all([ctx.waitForEvent('page'),p.locator('#quick-save').click()]);
      await next.waitForLoadState(); await review.close(); review=next;
      assert.equal(await review.locator('.print-item').count(),4);
    });
    await check('Validation rejects wrong patient, invalid quantities, roles, stale edit and storage failure', async () => {
      const results = await p.evaluate(id => {
        const p=Pema.patient('P001'), o=PemaOps.order('P001',id);
        const baseline=JSON.stringify(Pema.state);
        const failures=[];
        for(const fn of [
          ()=>PemaOps.saveOrder('missing',o.items,{}),
          ()=>PemaOps.saveOrder('P001',[{...o.items[0],quantity:1.5}],{}),
          ()=>PemaOps.saveOrder('P001',[{...o.items[0],quantity:0}],{}),
          ()=>PemaOps.saveOrder('P001',[{...o.items[0],quantity:Infinity}],{}),
          ()=>PemaOps.saveOrder('P001',[{...o.items[0],route:'bad',routeReason:'test'}],{}),
          ()=>PemaOps.saveOrder('P001',[{productId:'missing',quantity:1}],{}),
          ()=>PemaOps.approveOrder('P001',id,{role:'cashier',name:o.doctor}),
          ()=>PemaOps.saveOrder('P001',o.items,{id,version:0}),
        ]) { try{fn();failures.push('not rejected')}catch(e){failures.push(e.message)} }
        const unchanged=baseline===JSON.stringify(Pema.state);
        const save=Pema.save; Pema.save=()=>false;
        try{PemaOps.saveOrder('P001',o.items,{diagnosis:'test'});failures.push('not rejected')}catch(e){failures.push(e.message)}finally{Pema.save=save}
        return {failures,unchanged,rollback:baseline===JSON.stringify(Pema.state)};
      },orderId);
      assert.ok(results.unchanged);assert.ok(results.rollback);assert.equal(results.failures.length,9);assert.ok(results.failures.every(x=>x!=='not rejected'));
    });
    await check('Doctor approval, persistent mobile groups and immutable issued order', async () => {
      await review.locator('#approve').click();
      assert.equal(await review.locator('[data-print="all"]').isEnabled(),true);
      await mobile.reload();
      assert.equal(await mobile.locator('[data-mobile-order]').count(),1);
      assert.equal(await mobile.locator('.order-mobile-group').count(),2);
      assert.equal(await mobile.locator('.order-mobile-group p').count(),4);
      assert.match(await mobile.locator('[data-mobile-order]').textContent(), /Ghi chú riêng/);
      const state = await p.evaluate(id => {Pema.reload();const o=PemaOps.order('P001',id);let blocked=false;try{PemaOps.saveOrder('P001',o.items,{id,version:o.version})}catch(e){blocked=true}return {status:o.status,blocked,reviewedAt:o.reviewedAt}},orderId);
      assert.equal(state.status,'approved');assert.ok(state.blocked);assert.ok(state.reviewedAt);
      await mobile.setViewportSize({width:390,height:844});
      assert.ok(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await mobile.screenshot({path:path.join(out,'mobile-approved.png'),fullPage:true});
    });
    await check('Approval guards, idempotence, paid-draft guard and HTML escaping', async () => {
      const result = await p.evaluate(() => {
        const product=PemaProducts.get('H002'), rejected=[];
        const attempt=fn=>{try{fn();rejected.push(false)}catch(e){rejected.push(true)}};
        const make=(line={},meta={})=>PemaOps.saveOrder('P001',[{productId:product.id,quantity:1,usage:'Hướng dẫn test',...line}],{diagnosis:'Test',...meta});
        const missing=make({usage:''});attempt(()=>PemaOps.approveOrder('P001',missing.id,{role:'doctor',name:missing.doctor}));
        const noDiagnosis=make({},{diagnosis:''});attempt(()=>PemaOps.approveOrder('P001',noDiagnosis.id,{role:'doctor',name:noDiagnosis.doctor}));
        const excluded=make({route:'NONE',routeReason:'Test'});attempt(()=>PemaOps.approveOrder('P001',excluded.id,{role:'doctor',name:excluded.doctor}));
        const wrongDoctor=make();attempt(()=>PemaOps.approveOrder('P001',wrongDoctor.id,{role:'doctor',name:'BS. Mai'}));
        const paid=make();PemaOps.pay('P001',paid.invoiceId,1000,'Tiền mặt');attempt(()=>PemaOps.saveOrder('P001',paid.items,{id:paid.id,version:paid.version}));
        const html=make({usage:'<img src=x onerror="window.injected=true"> & giữ nguyên'},{diagnosis:'<script>window.injected=true</script>'});
        PemaOps.approveOrder('P001',html.id,{role:'doctor',name:html.doctor});
        const version=PemaOps.order('P001',html.id).version;
        PemaOps.approveOrder('P001',html.id,{role:'doctor',name:html.doctor});
        return {rejected,id:html.id,idempotent:version===PemaOps.order('P001',html.id).version};
      });
      assert.equal(result.rejected.length,5);assert.ok(result.rejected.every(Boolean));assert.ok(result.idempotent);
      const tab=await ctx.newPage();await tab.goto(`${base}/order-review/?patient=P001&order=${result.id}`);
      assert.equal(await tab.locator('#review-error').textContent(),'');
      assert.equal(await tab.locator('.item-usage img').count(),0);assert.equal(await tab.evaluate(()=>!!window.injected),false);
      assert.match(await tab.locator('.item-usage').textContent(),/<img/);await tab.close();
    });
    await check('Selective A5 PDF output and consultation terminology', async () => {
      for(const [filter,name,count] of [['PRESCRIPTION','prescription',1],['CONSULTATION','consultation',3],['all','mixed',4]]) {
        await review.evaluate(filter=>document.body.dataset.printFilter=filter,filter);
        await review.emulateMedia({media:'print'});
        assert.equal(await review.locator('.print-item:visible').count(),count);
        await review.pdf({path:path.join(out,name+'.pdf'),preferCSSPageSize:true,printBackground:true});
        await review.emulateMedia({media:'screen'});
      }
      assert.match(await review.locator('[data-doc="CONSULTATION"]').textContent(),/Bác sĩ tư vấn/);
      for(const [width,height] of [[1920,1020],[1440,900],[1280,720],[1024,768],[390,844]]) {
        await review.setViewportSize({width,height});
        assert.ok(await review.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        await review.screenshot({path:path.join(out,`review-${width}.png`)});
      }
    });
    await check('Five items fit one A5; long content flows and keeps footer, NONE excluded only from print', async () => {
      for(const [name,n,long] of [['five',5,false],['long',24,true],['oversize',1,true]]) {
        const id=await p.evaluate(({n,long,name})=>{
          const records=PemaProducts.records.filter(r=>r.outputType==='CONSULTATION').slice(0,n);
          const items=records.map(r=>({productId:r.id,quantity:1,usage:long?'Nội dung kiểm thử dài, giữ nguyên cách dùng. '.repeat(name==='oversize'?220:8):'Dùng theo hướng dẫn thử nghiệm.'}));
          items.push({productId:PemaProducts.get('H002').id,quantity:2,route:'NONE',routeReason:'Không in theo yêu cầu thử nghiệm'});
          const o=PemaOps.saveOrder('P001',items,{diagnosis:'Kiểm thử phân trang',note:'FOOTER_END_MARKER'});
          PemaOps.approveOrder('P001',o.id,{role:'doctor',name:o.doctor});return o.id;
        },{n,long,name});
        const tab=await ctx.newPage();await tab.goto(`${base}/order-review/?patient=P001&order=${id}`);
        assert.equal(await tab.locator('.print-item').count(),n);
        assert.match(await tab.locator('#review-excluded').textContent(),/Không in/);
        await tab.pdf({path:path.join(out,name+'.pdf'),preferCSSPageSize:true});
        await tab.close();
      }
    });
    await check('Browser print actions call print only after approval', async () => {
      await review.evaluate(()=>{window.print=()=>window.printCalls=(window.printCalls||0)+1});
      await review.locator('[data-print="CONSULTATION"]').click();
      await review.waitForFunction(()=>window.printCalls===1);
      assert.equal(await review.evaluate(()=>document.body.dataset.printFilter),'CONSULTATION');
    });
    await check('Invalid review URLs handled with disabled printing', async () => {
      await review.goto(`${base}/order-review/?patient=missing&order=missing`);
      assert.match(await review.locator('#review-error').textContent(),/Không tìm thấy/);
      assert.equal(await review.locator('[data-print="all"]').isDisabled(),true);
    });
    assert.deepEqual(report.errors,[]);
  } finally {await browser.close(); fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(report,null,2));}
})().catch(e=>{console.error(e);process.exitCode=1});
