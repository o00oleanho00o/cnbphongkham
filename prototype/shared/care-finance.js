/* Patient-linked services, prescriptions and deposit semantics for the demo. */
(() => {
  const P = window.Pema;
  if (!P) return;
  const DAY = '2026-09-20';
  let syncing = false;
  const esc = P.esc;
  const money = n => P.money(Number(n) || 0);
  const uid = prefix => prefix + Date.now().toString(36).toUpperCase();

  function serviceCatalog() {
    try { return window.PemaOps.seed().services; } catch (_) { return []; }
  }

  function makePlan(p, index) {
    const catalog = serviceCatalog();
    const procedure = String(p.procedure || '').toLowerCase();
    const service = catalog.find(s => s.name === p.procedure)
      || (procedure.includes('laser') && catalog.find(s => s.id === 'S2'))
      || (procedure.includes('chăm sóc') && catalog.find(s => s.id === 'S3'))
      || (procedure.includes('tái khám') && catalog.find(s => s.id === 'S0'))
      || (procedure.includes('tư vấn') && catalog.find(s => s.id === 'S1'))
      || catalog[index % Math.max(1, catalog.length)]
      || {id:'S-DEMO', name:p.procedure, price:1200000, duration:45};
    const listPrice = service.price * p.total;
    const discount = index === 0 ? 500000 : index % 4 === 0 ? 300000 : 0;
    return {
      id: 'LP-' + p.id,
      serviceId: service.id,
      serviceName: service.name,
      sessionsTotal: p.total,
      sessionsUsed: p.completed,
      listPrice,
      discount,
      agreedPrice: Math.max(0, listPrice - discount),
      depositApplied: index === 0 ? 4000000 : 0,
      status: p.completed >= p.total ? 'completed' : 'active',
      startedAt: '2026-06-26',
      doctor: p.doctor,
      invoiceIds: p.invoices.map(i => i.id)
    };
  }

  function makePrescription(p, index) {
    if (index % 5 === 1) return {
      id: 'DT-' + p.id,
      status: 'draft',
      prescribedAt: DAY,
      doctor: p.doctor,
      indication: 'Đang chờ bác sĩ kiểm tra trước khi gửi',
      items: [{name:'Cicaderm Cream 40ml', dose:'Bôi lớp mỏng', frequency:'Sáng và tối', duration:'14 ngày', quantity:1, unit:'tuýp'}]
    };
    if (index % 3 !== 0 && index !== 0) return null;
    return {
      id: 'DT-' + p.id,
      status: 'approved',
      prescribedAt: p.lastVisit || DAY,
      doctor: p.doctor,
      reviewedBy: p.doctor,
      reviewedAt: p.lastVisit || DAY,
      indication: 'Chăm sóc và phục hồi sau buổi điều trị',
      items: [
        {name:'Cicaderm Cream 40ml', dose:'Bôi lớp mỏng vùng cần chăm sóc', frequency:'Sáng và tối', duration:'14 ngày', quantity:1, unit:'tuýp'},
        {name:'Fudareus B 15g', dose:'Bôi theo vùng bác sĩ đã dặn', frequency:'Buổi tối', duration:'7 ngày', quantity:1, unit:'tuýp'}
      ]
    };
  }

  function hydrate() {
    if (syncing) return false;
    P.reload();
    let changed = false;
    P.state.patients.forEach((p, index) => {
      if (!Array.isArray(p.servicePlans)) { p.servicePlans = [makePlan(p, index)]; changed = true; }
      const primary = p.servicePlans[0];
      if (primary) {
        const next = p.completed;
        if (primary.sessionsUsed !== next) { primary.sessionsUsed = next; changed = true; }
        if (!Array.isArray(primary.invoiceIds)) { primary.invoiceIds = p.invoices.map(i => i.id); changed = true; }
        // Payments are projected from the invoice ledger in planPanel. Writing a
        // cached total here lets a reading mobile tab overwrite newer orders.
      }
      if (!Array.isArray(p.prescriptions)) { p.prescriptions = []; const rx = makePrescription(p, index); if (rx) p.prescriptions.push(rx); changed = true; }
      if (!Array.isArray(p.depositLedger)) { p.depositLedger = index === 0 ? [{id:'DEP-P001', received:4000000, applied:4000000, date:'2026-08-22', method:'Chuyển khoản'}] : []; changed = true; }
    });
    if (changed) { syncing = true; P.save(); syncing = false; }
    return changed;
  }

  function patient() { return P.patient(); }
  function activePage() { return document.body.dataset.page === 'patient'; }
  function emitRender() { window.dispatchEvent(new Event('pema-external')); }
  function totalReceived(p) { return p.invoices.reduce((sum, i) => sum + (i.paid ? i.amount : Number(i.received) || 0), 0); }
  function planPanel(p) {
    const plans = p.servicePlans || [];
    return `<section class="panel linked-care-panel" data-linked-panel="services"><div class="panel-head"><div class="panel-title">Dịch vụ & liệu trình<small>Giá chốt, số buổi và liên kết thu ngân</small></div><button class="btn btn-primary" data-care-action="add-service">＋ Thêm dịch vụ</button></div>${plans.map((x, i) => {
      const percent = x.sessionsTotal ? Math.min(100, Math.round(x.sessionsUsed / x.sessionsTotal * 100)) : 0;
      const received = (x.invoiceIds || []).reduce((sum, invoiceId) => { const invoice = (p.invoices || []).find(item => item.id === invoiceId); return sum + (invoice ? (invoice.paid ? invoice.amount : Number(invoice.received) || 0) : 0); }, 0);
      const due = Math.max(0, x.agreedPrice - received - (Number(x.depositApplied) || 0));
      return `<article class="linked-plan"><div class="linked-plan-main"><div class="linked-plan-kicker">${i === 0 ? 'LIỆU TRÌNH HIỆN TẠI' : 'DỊCH VỤ BỔ SUNG'} · ${esc(x.id)}</div><h3>${esc(x.serviceName)}</h3><div class="linked-plan-meta"><span>${x.sessionsUsed}/${x.sessionsTotal} buổi</span><span>${money(x.agreedPrice)} sau giảm</span><span>${x.status === 'active' ? 'Đang thực hiện' : 'Hoàn tất'}</span></div><div class="progress linked-progress"><i style="width:${percent}%"></i></div></div><div class="linked-plan-finance"><span>Đã thu</span><strong>${money(Math.min(received + (Number(x.depositApplied) || 0), x.agreedPrice))}</strong><small>${due ? 'Còn ' + money(due) : 'Đã đủ tiền'}</small></div></article>`;
    }).join('') || '<div class="empty">Chưa có dịch vụ gắn với hồ sơ.</div>'}<div class="linked-total"><span>Tiền cọc đã phân bổ</span><strong>${money((p.depositLedger || []).reduce((s, x) => s + (x.applied || 0), 0))}</strong><button class="btn btn-quiet" data-care-nav="cashier">Mở thu ngân →</button></div></section>`;
  }

  function prescriptionPanel(p) {
    const list = p.prescriptions || [];
    return `<section class="panel linked-care-panel" data-linked-panel="prescriptions"><div class="panel-head"><div class="panel-title">Đơn thuốc<small>Chỉ đơn đã duyệt mới xuất hiện trên Patient Mobile</small></div><button class="btn" data-care-action="add-prescription">＋ Tạo đơn nháp</button></div>${list.map(rx => `<article class="linked-rx"><div class="linked-rx-head"><div><div class="linked-plan-kicker">${esc(rx.id)} · ${P.date(rx.prescribedAt)}</div><h3>${rx.status === 'approved' ? 'Đơn đã duyệt' : 'Bản nháp cần bác sĩ duyệt'}</h3></div><span class="rx-status ${rx.status}">${rx.status === 'approved' ? 'Đã duyệt' : 'Chờ duyệt'}</span></div><p class="linked-rx-note">${esc(rx.indication || 'Chưa có chỉ định')}</p><ul>${(rx.items || []).map(i => `<li><strong>${esc(i.name)}</strong><span>${esc(i.dose)} · ${esc(i.frequency)} · ${esc(i.duration)}</span></li>`).join('')}</ul>${rx.status === 'draft' ? `<button class="btn btn-primary" data-care-action="approve-prescription" data-rx-id="${esc(rx.id)}">✓ Bác sĩ duyệt & gửi app</button>` : `<small class="linked-rx-review">Đã duyệt bởi ${esc(rx.reviewedBy || rx.doctor)} · người bệnh có thể xem trên app</small>`}</article>`).join('') || '<div class="empty">Chưa có đơn thuốc.</div>'}</section>`;
  }

  function injectClinic() {
    if (!activePage()) return;
    const p = patient();
    const old = document.querySelector('[data-linked-workspace]');
    if (old) old.remove();
    const content = document.querySelector('.content');
    const anchor = document.querySelector('.patient-layout');
    if (!content) return;
    const wrap = document.createElement('div');
    wrap.dataset.linkedWorkspace = 'true';
    wrap.className = 'linked-workspace';
    wrap.innerHTML = planPanel(p) + prescriptionPanel(p) + window.PemaOrderUI.history(p);
    if (anchor && anchor.parentElement === content) content.insertBefore(wrap, anchor.nextSibling);
    else content.appendChild(wrap);
  }

  function injectMobile() {
    if (!document.body.classList.contains('patient-page')) return;
    const app = document.querySelector('.mobile-app');
    const content = document.querySelector('#patient-content');
    if (!app || !content) return;
    content.querySelectorAll('[data-mobile-linked]').forEach(x => x.remove());
    if (!['docs', 'profile', 'home'].includes(app.dataset.currentScreen)) return;
    const p = patient();
    const approved = (p.prescriptions || []).filter(rx => rx.status === 'approved');
    const orders = (p.quickOrders || []).filter(o => o.status === 'approved');
    const approvedCount = approved.length + orders.length;
    const section = document.createElement('section');
    section.className = 'mobile-card mobile-linked-prescriptions';
    section.dataset.mobileLinked = 'true';
    section.innerHTML = `<div class="mobile-card-head"><h3>Đơn & phiếu đã duyệt</h3><span class="chip chip-soft">${approvedCount ? approvedCount + ' đơn' : 'Chưa có'}</span></div>${approved.map(rx => `<div class="mobile-rx"><strong>${esc(rx.id)} · ${P.date(rx.prescribedAt)}</strong><small>Bác sĩ ${esc(rx.reviewedBy || rx.doctor)}</small>${(rx.items || []).map(i => `<p><b>${esc(i.name)}</b><br>${esc(i.dose)} · ${esc(i.frequency)} · ${esc(i.duration)}</p>`).join('')}</div>`).join('') || (orders.length ? '' : '<p class="subtitle">Đơn và phiếu sẽ xuất hiện sau khi bác sĩ duyệt.</p>')}`;
    section.innerHTML += orders.map(o => `<div class="mobile-rx" data-mobile-order="${esc(o.id)}"><strong>${P.date(o.createdAt)}</strong><small>Đã duyệt bởi ${esc(o.reviewedBy)} · ${P.date(o.reviewedAt)}</small>${['PRESCRIPTION','CONSULTATION'].map(route => { const items=o.items.filter(x=>x.route===route); return items.length ? `<div class="order-mobile-group"><h4>${route==='PRESCRIPTION'?'Đơn thuốc':'Phiếu tư vấn'}</h4>${items.map(x=>`<p><b>${esc(x.name)}</b> · ${x.quantity} ${esc(x.unit)}<br>${esc(x.usage)}${x.note?'<br>'+esc(x.note):''}</p>`).join('')}</div>` : ''; }).join('')}${o.note?`<p>${esc(o.note)}</p>`:''}</div>`).join('');
    content.appendChild(section);
  }

  function modal(html) {
    document.querySelectorAll('.linked-modal').forEach(x => x.remove());
    document.body.insertAdjacentHTML('beforeend', `<div class="modal-backdrop linked-modal"><div class="modal linked-modal-card">${html}</div></div>`);
    document.querySelector('.linked-modal .modal-close')?.addEventListener('click', closeModal);
  }
  function closeModal() { document.querySelectorAll('.linked-modal').forEach(x => x.remove()); }
  function addService() {
    const options = serviceCatalog().map(s => `<option value="${esc(s.id)}" data-price="${s.price}">${esc(s.name)} · ${money(s.price)}/buổi</option>`).join('');
    modal(`<div class="modal-head"><div><div class="eyebrow">Patient 360 · dịch vụ</div><h2>Thêm dịch vụ vào liệu trình</h2></div><button class="modal-close">×</button></div><form id="linked-service-form"><div class="field"><label>Dịch vụ</label><select id="linked-service">${options}</select></div><div class="two-col-form"><div class="field"><label>Số buổi</label><input id="linked-sessions" type="number" min="1" max="20" value="3"></div><div class="field"><label>Giảm giá (₫)</label><input id="linked-discount" type="number" min="0" step="10000" value="0"></div></div><p class="notice">Giá đã chốt được lưu trên hồ sơ; thay đổi danh mục sau này không làm đổi liệu trình đã đăng ký.</p><button class="btn btn-primary" type="submit">Lưu dịch vụ</button></form>`);
    document.querySelector('#linked-service-form').onsubmit = e => { e.preventDefault(); const p = patient(), sel = document.querySelector('#linked-service'), s = serviceCatalog().find(x => x.id === sel.value); const total = Number(document.querySelector('#linked-sessions').value), discount = Number(document.querySelector('#linked-discount').value) || 0; if (!s || !Number.isInteger(total) || total < 1 || total > 20 || discount < 0 || discount > s.price * total) return; p.servicePlans = p.servicePlans || []; const planId = uid('LP-'), invoiceId = uid('HD-'); const agreedPrice = s.price * total - discount; p.invoices = p.invoices || []; p.invoices.unshift({id:invoiceId, date:DAY, label:`${s.name} · ${total} buổi`, amount:agreedPrice, received:0, paid:false, planId}); p.servicePlans.push({id:planId, serviceId:s.id, serviceName:s.name, sessionsTotal:total, sessionsUsed:0, listPrice:s.price*total, discount, agreedPrice, depositApplied:0, status:'active', startedAt:DAY, doctor:p.doctor, invoiceIds:[invoiceId]}); P.addEvent(p,'plan','Đã thêm dịch vụ vào liệu trình',`${s.name} · ${total} buổi · hóa đơn ${invoiceId}`,'Lễ tân'); P.log('Thêm dịch vụ vào liệu trình',p.id); P.save(); closeModal(); emitRender(); };
  }
  function addPrescription() { window.PemaOpsUI.openQuickOrder(patient().id); }
  function approvePrescription(id) { const p = patient(), rx = (p.prescriptions || []).find(x => x.id === id); if (!rx) return; rx.status = 'approved'; rx.reviewedBy = p.doctor; rx.reviewedAt = DAY; rx.indication = rx.indication === 'Cần bác sĩ kiểm tra trước khi gửi' ? 'Đã được bác sĩ kiểm tra và duyệt' : rx.indication; P.addEvent(p,'prescription','Bác sĩ đã duyệt đơn thuốc',rx.items.map(x=>x.name).join(', '),p.doctor); P.log('Duyệt đơn thuốc',p.id); P.save(); emitRender(); }
  function handle(e) {
    const btn = e.target.closest('[data-care-action],[data-care-nav]');
    if (!btn) return;
    if (btn.dataset.careAction === 'add-service') addService();
    if (btn.dataset.careAction === 'add-prescription') addPrescription();
    if (btn.dataset.careAction === 'approve-prescription') approvePrescription(btn.dataset.rxId);
    if (btn.dataset.careNav === 'cashier') window.location.href = '?screen=cashier';
  }
  function render() { hydrate(); injectClinic(); injectMobile(); }
  document.addEventListener('click', handle);
  window.addEventListener('pema-external', render);
  window.addEventListener('pema-change', () => { if (!syncing) render(); });
  const observer = new MutationObserver(() => {
    if (!document.querySelector('[data-linked-workspace]') && activePage()) setTimeout(injectClinic, 0);
    const app = document.querySelector('.mobile-app');
    if (document.body.classList.contains('patient-page') && app && ['docs','profile','home'].includes(app.dataset.currentScreen) && !document.querySelector('[data-mobile-linked]')) setTimeout(injectMobile, 0);
  });
  observer.observe(document.documentElement, {childList:true, subtree:true});
  render();
})();
