import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/finance_provider.dart';

class ProcedureForm extends ConsumerStatefulWidget {
  const ProcedureForm({
    super.key,
    this.initialPatient = 'P001',
    this.patientIds,
  });
  final String initialPatient;
  final List<String>? patientIds;
  @override
  ConsumerState<ProcedureForm> createState() => _ProcedureFormState();
}

class _ProcedureFormState extends ConsumerState<ProcedureForm> {
  final form = GlobalKey<FormState>();
  final gross = TextEditingController(),
      discount = TextEditingController(text: '0'),
      note = TextEditingController(),
      share = TextEditingController(text: '100'),
      rate = TextEditingController(),
      rate2 = TextEditingController(text: '0');
  String service = 'S0',
      patient = 'P001',
      doctor = 'D0',
      assistant = '',
      invoice = '',
      day = '';
  bool saving = false;
  @override
  void initState() {
    super.initState();
    final d = ref.read(financeProvider).data!;
    day = d['today'];
    patient = widget.initialPatient;
    gross.text = '${d['services'][0]['price']}';
    rate.text = '${d['services'][0]['rate'] / 100}';
  }

  @override
  void dispose() {
    for (final c in [gross, discount, note, share, rate, rate2]) {
      c.dispose();
    }
    super.dispose();
  }

  Widget field(String label, TextEditingController c, {bool number = true}) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: TextFormField(
          controller: c,
          keyboardType: number ? TextInputType.number : TextInputType.text,
          decoration: InputDecoration(labelText: label),
          validator: (v) => v == null || v.trim().isEmpty
              ? 'Cần nhập trường này'
              : number &&
                    (double.tryParse(v) == null || !double.parse(v).isFinite)
              ? 'Nhập số hợp lệ'
              : null,
        ),
      );
  Widget select(
    String label,
    String value,
    List<DropdownMenuItem<String>> items,
    void Function(String) onChange,
  ) => Padding(
    padding: const EdgeInsets.only(bottom: 14),
    child: DropdownButtonFormField<String>(
      initialValue: value,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: items,
      onChanged: (v) => setState(() => onChange(v!)),
    ),
  );
  @override
  Widget build(BuildContext context) {
    final c = ref.watch(financeProvider), d = c.data!;
    final finance = ref.read(financeProvider.notifier);
    final doctors = (d['doctors'] as List)
        .map(
          (x) =>
              DropdownMenuItem<String>(value: x['id'], child: Text(x['name'])),
        )
        .toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Ghi lượt đã thực hiện')),
      body: SafeArea(
        child: Form(
          key: form,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              select(
                'Hồ sơ',
                patient,
                {
                      ...(widget.patientIds ??
                          List.generate(
                            36,
                            (i) => 'P${(i + 1).toString().padLeft(3, '0')}',
                          )),
                      widget.initialPatient,
                    }
                    .map((id) => DropdownMenuItem(value: id, child: Text(id)))
                    .toList(),
                (v) => patient = v,
              ),
              select(
                'Thủ thuật',
                service,
                (d['services'] as List)
                    .map(
                      (s) => DropdownMenuItem<String>(
                        value: s['id'],
                        child: Text(s['name']),
                      ),
                    )
                    .toList(),
                (v) {
                  service = v;
                  final s = (d['services'] as List).firstWhere(
                    (s) => s['id'] == v,
                  );
                  gross.text = '${s['price']}';
                  rate.text = '${s['rate'] / 100}';
                },
              ),
              TextButton.icon(
                onPressed: () async {
                  final date = await showDatePicker(
                    context: context,
                    initialDate: DateTime.parse(day),
                    firstDate: DateTime(2020),
                    lastDate: DateTime.parse(d['today']),
                  );
                  if (date != null)
                    setState(
                      () => day = date.toIso8601String().substring(0, 10),
                    );
                },
                icon: const Icon(Icons.calendar_month),
                label: Text('Ngày thực hiện $day'),
              ),
              field('Giá niêm yết (VND)', gross),
              field('Giảm giá (VND)', discount),
              select('Gắn hóa đơn đã có', invoice, [
                const DropdownMenuItem(
                  value: '',
                  child: Text('Tạo hóa đơn mới cho lượt này'),
                ),
                ...(d['invoices'] as List).map(
                  (i) => DropdownMenuItem<String>(
                    value: i['id'],
                    child: Text(
                      '${i['patient']} · ${i['id']}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ], (v) => invoice = v),
              select('Bác sĩ chính', doctor, doctors, (v) => doctor = v),
              field('Tỷ trọng doanh số bác sĩ chính %', share),
              field('Tỷ lệ tiền bác sĩ chính %', rate),
              select('Người phối hợp', assistant, [
                const DropdownMenuItem(value: '', child: Text('Không có')),
                ...doctors,
              ], (v) => assistant = v),
              if (assistant.isNotEmpty)
                field('Tỷ lệ tiền người phối hợp %', rate2),
              const Text(
                'Người phối hợp nhận phần tỷ trọng doanh số còn lại. Tổng tỷ lệ tiền không quá 100%.',
                style: TextStyle(fontSize: 12),
              ),
              const SizedBox(height: 12),
              field('Ghi chú xác nhận hoàn tất', note, number: false),
              if (c.error.isNotEmpty)
                Text(c.error, style: const TextStyle(color: Colors.deepOrange)),
              FilledButton(
                onPressed: saving
                    ? null
                    : () async {
                        if (!form.currentState!.validate()) return;
                        setState(() => saving = true);
                        final sh = (double.parse(share.text) * 100).round();
                        final ok = await finance.command('entry', {
                          'patient': patient,
                          'invoice': invoice,
                          'service': service,
                          'date': day,
                          'list': int.tryParse(gross.text) ?? -1,
                          'discount': int.tryParse(discount.text) ?? -1,
                          'note': note.text,
                          'people': [
                            {
                              'doctor': doctor,
                              'share': sh,
                              'rate': (double.parse(rate.text) * 100).round(),
                            },
                            if (assistant.isNotEmpty)
                              {
                                'doctor': assistant,
                                'share': 10000 - sh,
                                'rate': (double.parse(rate2.text) * 100)
                                    .round(),
                              },
                          ],
                        });
                        if (mounted) {
                          setState(() => saving = false);
                          if (ok) Navigator.pop(context);
                        }
                      },
                child: const Text('Ghi nhận • Chờ kế toán duyệt'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
