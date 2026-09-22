(() => {
  const P = window.Pema, O = window.PemaOps, esc = P.esc;
  const labels = {PRESCRIPTION:'Đơn thuốc', CONSULTATION:'Phiếu tư vấn', NONE:'Không in', UNRESOLVED:'Cần phân loại'};
  function preview(patientId, id) {
    const url = `../order-review/?patient=${encodeURIComponent(patientId)}&order=${encodeURIComponent(id)}`;
    const tab = window.open(url, '_blank');
    if (!tab) window.location.assign(url);
  }
  function history(p) {
    const orders = p ? (p.quickOrders || []).map(o => ({p,o})) : P.state.patients.flatMap(p => (p.quickOrders || []).map(o => ({p,o})));
    orders.sort((a,b) => b.o.createdAt.localeCompare(a.o.createdAt));
    return `<section class="panel order-history"><div class="panel-title">Đơn thuốc & phiếu tư vấn<small>Nháp → bác sĩ duyệt → in và hiển thị trên app</small></div>${orders.map(({p,o}) => `<article class="order-history-row"><div><strong>${esc(p.name)}</strong><small>${P.date(o.createdAt)} · ${o.items.length} sản phẩm · ${o.status === 'approved' ? 'Đã duyệt' : 'Bản nháp'}</small></div><div class="actions"><button class="btn" data-order-preview="${esc(o.id)}" data-order-patient="${esc(p.id)}">Xem / in</button>${o.status === 'draft' ? `<button class="btn" data-order-edit="${esc(o.id)}" data-order-patient="${esc(p.id)}">Sửa nháp</button>` : ''}</div></article>`).join('') || '<p class="empty">Chưa có đơn từ catalog.</p>'}</section>`;
  }
  function open(host, patientId = P.state.selected, orderId) {
    P.reload();
    const existing = orderId ? O.order(patientId, orderId) : null;
    const draft = {patient:patientId, doctor:existing?.doctor || P.patient(patientId).doctor,
      diagnosis:existing?.diagnosis ?? P.patient(patientId).concern, note:existing?.note || '',
      items:existing ? structuredClone(existing.items) : [], query:''};
    host.modal(`<div class="modal-backdrop"><div class="modal ops-modal order-modal"><div class="modal-head"><div><div class="eyebrow">Lên đơn từ danh mục Excel</div><h2>${existing ? 'Sửa đơn nháp' : 'Tạo đơn thuốc / phiếu tư vấn'}</h2></div><button class="modal-close" aria-label="Đóng hộp thoại">×</button></div><form id="catalog-order-form"><div class="two-col-form"><div class="field"><label for="quick-patient">Bệnh nhân</label><select id="quick-patient" ${existing ? 'disabled' : ''}>${P.state.patients.map(p => `<option value="${esc(p.id)}" ${p.id === patientId ? 'selected' : ''}>${esc(p.name)} · ${esc(p.id)}</option>`).join('')}</select></div><div class="field"><label for="quick-doctor">Bác sĩ phụ trách</label><select id="quick-doctor">${O.seed().doctors.map(d => `<option ${d.name === draft.doctor ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</select></div></div><div class="field"><label for="quick-diagnosis">Chẩn đoán / nội dung tư vấn</label><input id="quick-diagnosis" value="${esc(draft.diagnosis)}"></div><div class="quick-order-grid"><section><div class="field"><label for="quick-product-search">Tìm mã hoặc tên sản phẩm</label><input id="quick-product-search" placeholder="Ví dụ: H002, Cicaderm, TPCN" autocomplete="off"></div><p class="quick-catalog-note">${esc(window.PemaProducts.summary())}</p><div id="quick-results" class="quick-product-list"></div></section><section class="quick-cart"><div class="panel-title">Nội dung đơn<small>Nhập cách dùng trước khi bác sĩ duyệt</small></div><div id="quick-lines"></div><div class="quick-total"><span>Tổng tiền dự kiến</span><strong id="quick-total"></strong></div></section></div><div class="field"><label for="quick-note">Dặn dò chung</label><textarea id="quick-note">${esc(draft.note)}</textarea></div><p class="notice">Sản phẩm chưa có loại trong Excel cần được phân loại. “Không in” chỉ loại khỏi phiếu, vẫn tính trong hóa đơn. Đơn nháp chưa xuất hiện trên app.</p><p id="quick-error" role="alert" class="ops-error"></p><div class="quick-order-actions"><button type="button" class="btn" id="quick-cancel">Hủy</button><button type="submit" class="btn btn-primary" id="quick-save">Lưu nháp & xem tách đơn</button></div></form></div></div>`);
    const form = document.getElementById('catalog-order-form');
    const results = () => {
      document.getElementById('quick-results').innerHTML = window.PemaProducts.find(draft.query, 115).map(r => `<button type="button" class="quick-product-row" data-quick-add="${esc(r.code)}"><span><strong>${esc(r.name)}</strong><small>${esc(r.code)} · ${esc(r.unit)} · ${esc(r.sourceType || 'Chưa có loại')} · ${labels[r.outputType]}</small></span><b>${P.money(r.price)}</b></button>`).join('') || '<p class="empty">Không tìm thấy sản phẩm phù hợp.</p>';
    };
    const total = () => { document.getElementById('quick-total').textContent = P.money(draft.items.reduce((s,x) => s + (Number(x.quantity) || 0) * x.unitPrice, 0)); };
    const lines = () => {
      document.getElementById('quick-lines').innerHTML = draft.items.map((x,i) => `<article class="order-line" data-line="${i}"><div class="order-line-head"><strong>${i + 1}. ${esc(x.name)}</strong><button type="button" class="btn" data-quick-remove="${i}" aria-label="Xóa ${esc(x.code)}">×</button></div><small>${esc(x.code)} · ${esc(x.unit)} · ${P.money(x.unitPrice)}</small><div class="two-col-form"><div class="field"><label for="qty-${i}">Số lượng (${esc(x.unit)})</label><input id="qty-${i}" data-line-field="quantity" type="number" min="1" max="9999" step="1" required value="${x.quantity}"></div><div class="field"><label for="route-${i}">Loại phiếu</label><select id="route-${i}" data-line-field="route">${Object.entries(labels).map(([key,label]) => `<option value="${key}" ${x.route === key ? 'selected' : ''}>${label}</option>`).join('')}</select></div></div><div class="field"><label for="usage-${i}">Cách dùng / tần suất / thời gian</label><textarea id="usage-${i}" data-line-field="usage" placeholder="Nhập hướng dẫn đã được bác sĩ chỉ định">${esc(x.usage)}</textarea></div><div class="field"><label for="line-note-${i}">Ghi chú sản phẩm</label><input id="line-note-${i}" data-line-field="note" value="${esc(x.note)}"></div><div class="field"><label for="reason-${i}">Lý do đổi phân loại (nếu có)</label><input id="reason-${i}" data-line-field="routeReason" value="${esc(x.routeReason)}"></div></article>`).join('') || '<p class="empty">Chọn sản phẩm ở danh sách.</p>';
      total();
    };
    form.oninput = event => {
      const t = event.target;
      if (t.dataset.lineField) { draft.items[Number(t.closest('[data-line]').dataset.line)][t.dataset.lineField] = t.value; total(); }
      if (t.id === 'quick-product-search') { draft.query = t.value; results(); }
    };
    document.getElementById('quick-patient').onchange = event => {
      draft.patient = event.target.value;
      const p = P.patient(draft.patient);
      document.getElementById('quick-doctor').value = p.doctor;
      document.getElementById('quick-diagnosis').value = p.concern;
    };
    form.onclick = event => {
      const add = event.target.closest('[data-quick-add]'), remove = event.target.closest('[data-quick-remove]');
      if (add) {
        const r = window.PemaProducts.get(add.dataset.quickAdd), x = draft.items.find(x => x.code === r.code);
        if (x) x.quantity = Number(x.quantity) + 1;
        else draft.items.push({productId:r.id, code:r.code, name:r.name, unit:r.unit, unitPrice:r.price, catalogRoute:r.outputType, route:r.outputType, quantity:1, usage:'', note:'', routeReason:''});
        lines();
      }
      if (remove) { draft.items.splice(Number(remove.dataset.quickRemove), 1); lines(); }
    };
    form.onsubmit = event => {
      event.preventDefault();
      try {
        const result = O.saveOrder(draft.patient, draft.items, {id:existing?.id, version:existing?.version,
          doctor:document.getElementById('quick-doctor').value, diagnosis:document.getElementById('quick-diagnosis').value, note:document.getElementById('quick-note').value});
        host.close(); host.toast('Đã lưu nháp. Kiểm tra hai phiếu trước khi duyệt.'); preview(draft.patient, result.id);
      } catch (err) { document.getElementById('quick-error').textContent = err.message; }
    };
    document.getElementById('quick-cancel').onclick = () => host.close();
    results(); lines();
  }
  document.addEventListener('click', event => {
    const b = event.target.closest('[data-order-preview],[data-order-edit]');
    if (!b) return;
    if (b.dataset.orderPreview) preview(b.dataset.orderPatient, b.dataset.orderPreview);
    else window.PemaOpsUI.openQuickOrder(b.dataset.orderPatient, b.dataset.orderEdit);
  });
  window.PemaOrderUI = {open, preview, history};
})();
