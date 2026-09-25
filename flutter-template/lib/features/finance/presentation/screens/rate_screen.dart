import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/finance_provider.dart';

class RateScreen extends ConsumerStatefulWidget {
  const RateScreen({super.key});
  @override
  ConsumerState<RateScreen> createState() => _RateScreenState();
}

class _RateScreenState extends ConsumerState<RateScreen> {
  @override
  Widget build(BuildContext context) {
    final c = ref.watch(financeProvider);
    final finance = ref.read(financeProvider.notifier);
    return Scaffold(
      appBar: AppBar(title: const Text('Chính sách thủ thuật')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Text(
            'Thay đổi áp dụng cho lượt mới. Tỷ lệ lịch sử được giữ nguyên.',
          ),
          for (final s in c.data?['services'] ?? [])
            Card(
              child: ListTile(
                title: Text(s['name']),
                subtitle: Text(
                  '${s['rate'] / 100}% · ${s['basis']} · phiên bản ${s['version']}',
                ),
                trailing: const Icon(Icons.edit_outlined),
                onTap: () async {
                  final rate = TextEditingController(
                    text: '${s['rate'] / 100}',
                  );
                  String basis = s['basis'];
                  final value = await showDialog<Map<String, dynamic>>(
                    context: context,
                    builder: (ctx) => StatefulBuilder(
                      builder: (ctx, set) => AlertDialog(
                        title: Text(s['name']),
                        content: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            TextField(
                              controller: rate,
                              keyboardType: TextInputType.number,
                              decoration: const InputDecoration(
                                labelText: 'Tỷ lệ %',
                              ),
                            ),
                            DropdownButton<String>(
                              value: basis,
                              isExpanded: true,
                              items: const [
                                DropdownMenuItem(
                                  value: 'net',
                                  child: Text('Giá sau giảm'),
                                ),
                                DropdownMenuItem(
                                  value: 'list',
                                  child: Text('Giá niêm yết'),
                                ),
                                DropdownMenuItem(
                                  value: 'collected',
                                  child: Text('Theo thực thu'),
                                ),
                              ],
                              onChanged: (v) => set(() => basis = v!),
                            ),
                          ],
                        ),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(ctx),
                            child: const Text('Hủy'),
                          ),
                          FilledButton(
                            onPressed: () {
                              final n = double.tryParse(rate.text);
                              if (n != null && n >= 0 && n <= 100)
                                Navigator.pop(ctx, {
                                  'service': s['id'],
                                  'rate': (n * 100).round(),
                                  'basis': basis,
                                });
                            },
                            child: const Text('Lưu'),
                          ),
                        ],
                      ),
                    ),
                  );
                  rate.dispose();
                  if (value != null) await finance.command('rate', value);
                },
              ),
            ),
          if (c.error.isNotEmpty) Text(c.error),
        ],
      ),
    );
  }
}
