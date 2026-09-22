const normalize = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase().replace(/\s+/g, ' ').trim();
const records = rows;
const byCode = Object.fromEntries(records.map(r => [r.code, r]));
window.PemaProducts = {
  version: 3, filename: source.filename, source, records, byCode, normalize,
  counts: {totalRows: records.length, prescription: source.prescription, consultation: records.filter(r => r.outputType === 'CONSULTATION').length, unresolved: records.filter(r => r.outputType === 'UNRESOLVED').length},
  get(code) { return byCode[String(code || '').trim().toUpperCase()] || null; },
  route(record) { return record?.outputType || 'UNRESOLVED'; },
  find(query, limit = 20) {
    const q = normalize(query);
    return records.filter(r => !q || [r.code, r.name, r.sourceType].some(v => normalize(v).includes(q)))
      .sort((a, b) => Number(normalize(b.code) === q) - Number(normalize(a.code) === q)).slice(0, limit);
  },
  summary() { return `${records.length} sản phẩm · ${this.counts.prescription} thuốc · ${this.counts.consultation} sản phẩm tư vấn · ${this.counts.unresolved} cần phân loại`; }
};
