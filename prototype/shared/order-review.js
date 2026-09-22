(() => {
  const P = window.Pema, O = window.PemaOps, e = P.esc;
  const params = new URLSearchParams(location.search), patientId = params.get('patient'), orderId = params.get('order');
  let current;
  const lines = value => e(value).replace(/\r?\n/g, '<br>');
  function sheet(items, route) {
    const o = current.order, p = current.patient, consult = route === 'CONSULTATION';
    const title = consult ? 'PHIẾU TƯ VẤN' : 'ĐƠN THUỐC';
    if (!items.length) return '';
    return `<section class="document-set" data-doc="${route}"><h2 class="section-label">${title} · ${items.length} sản phẩm</h2><div class="section-scroll"><article class="order-sheet"><header class="sheet-header"><img src="../shared/assets/pema-logo.png" alt="Pema"><div><strong>PEMA DIGITAL CLINIC</strong><small>Phòng khám da liễu · dữ liệu demo</small></div></header><h1>${title}</h1>${o.status !== 'approved' ? '<p class="draft-mark">BẢN NHÁP — CHỜ BÁC SĨ DUYỆT</p>' : ''}<div class="patient-grid"><div><b>Họ tên:</b> ${e(p.name)}</div><div><b>Tuổi:</b> ${e(p.age)} · ${e(p.gender)}</div><div><b>Mã hồ sơ:</b> ${e(p.id)}</div><div><b>Ngày:</b> ${P.date(o.date || o.createdAt)}</div>${p.address ? `<div class="wide"><b>Địa chỉ:</b> ${e(p.address)}</div>` : ''}<div class="wide"><b>Chẩn đoán / nội dung tư vấn:</b> ${lines(o.diagnosis)}</div></div><div class="item-list">${items.map((x,i) => `<div class="print-item"><div class="item-line"><strong>${i + 1}. ${e(x.name)}</strong><span>× ${x.quantity} ${e(x.unit)}</span></div><div class="item-usage">${lines(x.usage || 'Chưa nhập cách dùng')}</div>${x.note ? `<div class="item-note">Ghi chú: ${lines(x.note)}</div>` : ''}</div>`).join('')}</div><footer class="print-footer"><div><b>Dặn dò:</b> ${lines(o.note)}</div><p>${consult ? 'Mang theo phiếu này khi tái khám. Kiểm tra sản phẩm trước khi nhận.' : 'Mang theo đơn này khi tái khám. Kiểm tra thuốc trước khi nhận.'}</p><div class="signature"><span>Ngày ${P.date(o.date || o.createdAt)}</span><strong>${consult ? 'Bác sĩ tư vấn' : 'Bác sĩ khám'}</strong><b>${e(o.reviewedBy || o.doctor)}</b></div></footer></article></div></section>`;
  }
  function refresh() {
    P.reload();
    try {
      if (!patientId || !orderId) throw Error('Thiếu mã bệnh nhân hoặc mã đơn.');
      current = O.orderPrintData(patientId, orderId);
      const o = current.order;
      document.title = `Tách đơn – ${current.patient.name}`;
      document.getElementById('review-title').textContent = document.title;
      document.getElementById('review-status').textContent = `${o.status === 'approved' ? 'Đã duyệt bởi ' + o.reviewedBy : 'Bản nháp · Bác sĩ phụ trách: ' + o.doctor} · A5 dọc 148 × 210 mm · ${o.items.length} sản phẩm`;
      let ready = false;
      if (o.status === 'approved') {
        try { O.orderPrintData(patientId, orderId, true); ready = true; } catch (_) { /* Invalid snapshots never print. */ }
      }
      document.body.dataset.approved = String(ready);
      document.getElementById('documents').innerHTML = sheet(current.prescription, 'PRESCRIPTION') + sheet(current.consultation, 'CONSULTATION');
      document.getElementById('review-excluded').innerHTML = (current.unresolved.length ? `<p class="warning">Cần phân loại ${current.unresolved.length} sản phẩm: ${current.unresolved.map(x=>e(x.name)).join('; ')}. Mở “Sửa nháp” trong hồ sơ hoặc thu ngân để xử lý.</p>` : '') + (current.excluded.length ? `<p>Không in (${current.excluded.length}): ${current.excluded.map(x => `${e(x.name)} — ${e(x.routeReason)}`).join('; ')}. Vẫn tính trong hóa đơn.</p>` : '');
      document.querySelectorAll('[data-print]').forEach(b => {
        const count = b.dataset.print === 'PRESCRIPTION' ? current.prescription.length : b.dataset.print === 'CONSULTATION' ? current.consultation.length : current.prescription.length + current.consultation.length;
        b.disabled = !ready || !count;
      });
      const approve = document.getElementById('approve');
      approve.hidden = o.status !== 'draft'; approve.disabled = !!current.unresolved.length;
      document.getElementById('review-error').textContent = '';
    } catch (err) {
      current = null; document.body.dataset.approved = 'false';
      document.getElementById('documents').innerHTML = '';
      document.getElementById('review-excluded').innerHTML = '';
      document.getElementById('approve').hidden = true;
      document.querySelectorAll('[data-print]').forEach(b => b.disabled = true);
      document.getElementById('review-error').textContent = err.message;
    }
  }
  document.getElementById('approve').onclick = () => {
    try {
      O.approveOrder(patientId, orderId, {role:'doctor', name:current.order.doctor});
      refresh();
    } catch(err) { document.getElementById('review-error').textContent = err.message; }
  };
  document.querySelectorAll('[data-print]').forEach(b => b.onclick = async () => {
    try {
      P.reload(); O.orderPrintData(patientId, orderId, true);
      document.body.dataset.printFilter = b.dataset.print;
      await document.fonts.ready;
      window.print();
    } catch(err) { document.getElementById('review-error').textContent = err.message; }
  });
  window.addEventListener('beforeprint', () => { refresh(); });
  window.addEventListener('afterprint', () => { delete document.body.dataset.printFilter; });
  window.addEventListener('pema-external', refresh);
  refresh();
})();
