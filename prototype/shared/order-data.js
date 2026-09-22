/* Catalog-backed order commands. All mutations use the shared transaction. */
(() => {
  const P = window.Pema, O = window.PemaOps;
  const routes = ['PRESCRIPTION', 'CONSULTATION', 'NONE', 'UNRESOLVED'];
  const text = value => String(value ?? '').trim();
  const today = () => new Date().toLocaleDateString('sv-SE');
  function patient(id) {
    const p = P.state.patients.find(p => p.id === id);
    if (!p) throw Error('Không tìm thấy bệnh nhân.');
    return p;
  }
  function order(patientId, id) {
    return (patient(patientId).quickOrders || []).find(o => o.id === id);
  }
  function validateItems(items, final = false) {
    if (!Array.isArray(items) || !items.length) throw Error('Chọn ít nhất một sản phẩm.');
    items.forEach((x, i) => {
      if (!x.name || !Number.isSafeInteger(x.quantity) || x.quantity < 1 || x.quantity > 9999) throw Error(`Dòng ${i + 1}: số lượng phải là số nguyên từ 1 đến 9999.`);
      if (!Number.isSafeInteger(x.unitPrice) || x.unitPrice < 0) throw Error(`Dòng ${i + 1}: giá không hợp lệ.`);
      if (!routes.includes(x.route)) throw Error(`Dòng ${i + 1}: phân loại không hợp lệ.`);
      if (final && x.route === 'UNRESOLVED') throw Error(`Dòng ${i + 1}: cần phân loại trước khi duyệt hoặc in.`);
      if (final && x.route !== 'NONE' && !text(x.usage)) throw Error(`Dòng ${i + 1}: cần cách dùng trước khi duyệt.`);
    });
    if (final && items.every(x => x.route === 'NONE')) throw Error('Đơn không có sản phẩm để phát hành.');
  }
  function saveOrder(patientId, items, meta = {}) {
    return O.transact(() => {
      const p = patient(patientId), existing = meta.id ? order(patientId, meta.id) : null;
      if (meta.id && (!existing || existing.status !== 'draft')) throw Error('Chỉ được sửa đơn nháp còn tồn tại.');
      if (existing && meta.version !== existing.version) throw Error('Đơn đã thay đổi ở cửa sổ khác. Hãy mở lại.');
      const clean = (items || []).map((line, index) => {
        const r = window.PemaProducts?.records.find(r => r.id === line.productId || (line.code && r.code === line.code));
        if (!r) throw Error(`Dòng ${index + 1}: chọn sản phẩm từ catalog.`);
        const previous = existing?.items.find(x => x.code === r.code);
        const catalogRoute = previous?.catalogRoute || r.outputType;
        const route = line.route || catalogRoute;
        const routeReason = text(line.routeReason);
        if (route !== catalogRoute && !routeReason) throw Error(`Dòng ${index + 1}: ghi lý do thay đổi phân loại.`);
        return {productId:r.id, code:r.code, name:previous?.name || r.name, sourceType:previous?.sourceType ?? r.sourceType,
          unit:previous?.unit ?? r.unit, rowNumber:r.rowNumber, catalogRoute, route, routeReason,
          quantity:Number(line.quantity), unitPrice:previous?.unitPrice ?? r.price, usage:text(line.usage), note:text(line.note)};
      });
      validateItems(clean);
      const doctor = text(meta.doctor || p.doctor);
      if (!O.seed().doctors.some(d => d.name === doctor)) throw Error('Chọn bác sĩ trong danh sách.');
      const total = clean.reduce((s, x) => s + x.quantity * x.unitPrice, 0);
      if (!Number.isSafeInteger(total)) throw Error('Tổng tiền không hợp lệ.');
      let invoice = existing && p.invoices.find(i => i.id === existing.invoiceId);
      if (existing && (!invoice || invoice.received > 0 || invoice.paid)) throw Error('Đơn đã thu tiền hoặc thiếu hóa đơn; không thể sửa.');
      const at = new Date().toISOString();
      const result = {...existing, id:existing?.id || 'OD-' + crypto.randomUUID(), patient:patientId,
        createdAt:existing?.createdAt || at, updatedAt:at, date:existing?.date || today(), doctor,
        diagnosis:text(meta.diagnosis), note:text(meta.note), items:clean, status:'draft',
        version:(existing?.version || 0) + 1, source:'catalog-order', catalogSource:window.PemaProducts.source};
      if (!invoice) {
        invoice = {id:'HD-' + crypto.randomUUID(), date:result.date, received:0, paid:false, orderId:result.id};
        p.invoices.unshift(invoice);
      }
      Object.assign(invoice, {amount:total, label:`Đơn sản phẩm · ${clean.length} dòng`});
      result.invoiceId = invoice.id;
      p.quickOrders ||= [];
      if (existing) p.quickOrders[p.quickOrders.indexOf(existing)] = result;
      else p.quickOrders.unshift(result);
      P.addEvent(p, 'order', existing ? 'Cập nhật đơn nháp' : 'Tạo đơn nháp từ catalog', result.id, doctor, result.date);
      P.log(existing ? 'Sửa đơn nháp' : 'Tạo đơn nháp', p.id);
      return result;
    });
  }
  function approveOrder(patientId, id, actor) {
    window.PemaStaff?.assert('clinical');
    return O.transact(() => {
      const p = patient(patientId), o = order(patientId, id);
      if (!actor || actor.role !== 'doctor' || !O.seed().doctors.some(d => d.name === actor.name)) throw Error('Cần bác sĩ duyệt đơn.');
      if (!o || !['draft', 'approved'].includes(o.status)) throw Error('Đơn không thể duyệt.');
      if (o.status === 'approved') return o;
      if (o.source !== 'catalog-order') throw Error('Đơn cũ cần mở Sửa nháp để đối chiếu lại catalog trước khi duyệt.');
      if (actor.name !== o.doctor) throw Error('Bác sĩ duyệt phải là bác sĩ phụ trách đơn.');
      validateItems(o.items, true);
      if (!text(o.diagnosis)) throw Error('Cần nội dung tư vấn / chẩn đoán trước khi duyệt.');
      o.status = 'approved'; o.reviewedBy = actor.name; o.reviewedAt = new Date().toISOString(); o.version = (o.version || 0) + 1;
      P.addEvent(p, 'prescription', 'Bác sĩ duyệt đơn và phiếu tư vấn', o.id, actor.name, today());
      P.log('Duyệt đơn và phiếu tư vấn', p.id);
      return o;
    });
  }
  function orderPrintData(patientId, id, requireApproved = false) {
    const o = order(patientId, id);
    if (!o) throw Error('Không tìm thấy đơn.');
    if (requireApproved) {
      validateItems(o.items, true);
      if (o.status !== 'approved') throw Error('Đơn nháp cần bác sĩ duyệt trước khi in.');
    }
    return {patient:patient(patientId), order:o, prescription:o.items.filter(x => x.route === 'PRESCRIPTION'),
      consultation:o.items.filter(x => x.route === 'CONSULTATION'), excluded:o.items.filter(x => x.route === 'NONE'),
      unresolved:o.items.filter(x => !routes.includes(x.route) || x.route === 'UNRESOLVED')};
  }
  Object.assign(O, {createQuickOrder:saveOrder, saveOrder, approveOrder, order, orderPrintData,
    routeForProduct:product => product?.outputType || 'UNRESOLVED'});
})();
