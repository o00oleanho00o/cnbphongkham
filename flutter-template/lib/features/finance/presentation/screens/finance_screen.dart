import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/utils/money_format.dart';
import '../../../../core/widgets/pema_bottom_nav.dart';
import '../../domain/models/finance_state.dart';
import '../providers/finance_provider.dart';
import 'procedure_form_screen.dart';
import 'rate_screen.dart';

const _statusLabels = {
  'open': 'Đang đối soát',
  'closed': 'Đã chốt',
  'paid': 'Đã chi',
  'pending': 'Chờ duyệt',
  'approved': 'Đã duyệt',
  'void': 'Đã hủy',
};

class FinanceScreen extends ConsumerStatefulWidget {
  const FinanceScreen({
    super.key,
    this.initialTab = 0,
    this.lockRole = false,
    this.patientIds,
  });
  final int initialTab;
  final bool lockRole;
  final List<String>? patientIds;
  @override
  ConsumerState<FinanceScreen> createState() => _FinanceScreenState();
}

class _FinanceScreenState extends ConsumerState<FinanceScreen> {
  FinanceNotifier get finance => ref.read(financeProvider.notifier);
  late FinanceState c;
  late int tab;
  String paymentKey = DateTime.now().microsecondsSinceEpoch.toString();
  @override
  void initState() {
    super.initState();
    tab = widget.initialTab;
    finance.refresh();
  }

  Widget card(List<Widget> children) => Container(
    margin: const EdgeInsets.only(bottom: 16),
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: const Color(0xFFD9E5EE)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: children,
    ),
  );
  Widget title(String text) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Text(
      text,
      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18),
    ),
  );
  Widget line(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Row(
      children: [
        Expanded(child: Text(label)),
        const SizedBox(width: 12),
        Flexible(
          child: Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
      ],
    ),
  );
  Future<void> run(String action, Map<String, dynamic> d) async {
    final ok = await finance.command(action, d);
    if (mounted && ok)
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Đã ghi nhận thành công')));
  }

  Future<String?> ask(String label) async {
    final input = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(label),
        content: TextField(controller: input, autofocus: true),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Quay lại'),
          ),
          FilledButton(
            onPressed: () {
              if (input.text.trim().isNotEmpty)
                Navigator.pop(ctx, input.text.trim());
            },
            child: const Text('Xác nhận'),
          ),
        ],
      ),
    );
    input.dispose();
    return result;
  }

  Future<void> changeMonth() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.parse('${c.month}-01'),
      firstDate: DateTime(2020),
      lastDate: DateTime(2035),
    );
    if (picked != null) {
      await finance.setMonth(picked.toIso8601String().substring(0, 7));
    }
  }

  @override
  Widget build(BuildContext context) {
    c = ref.watch(financeProvider);
    final data = c.data;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tài chính Pema'),
        actions: [
          IconButton(
            onPressed: () => finance.refresh(),
            icon: const Icon(Icons.refresh),
            tooltip: 'Làm mới',
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: finance.refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              const Text(
                'Vai trò mẫu • dữ liệu dùng chung với web',
                style: TextStyle(fontSize: 12, color: Color(0xFF5D7184)),
              ),
              const SizedBox(height: 8),
              if (!widget.lockRole)
                DropdownButtonFormField<String>(
                  initialValue: '${c.role}:${c.doctor}',
                  isExpanded: true,
                  items: const [
                    DropdownMenuItem(
                      value: 'owner:D0',
                      child: Text('BS. Tâm · Chủ phòng khám'),
                    ),
                    DropdownMenuItem(
                      value: 'accountant:D0',
                      child: Text('Kế toán'),
                    ),
                    DropdownMenuItem(
                      value: 'doctor:D0',
                      child: Text('BS. Tâm · Cá nhân'),
                    ),
                    DropdownMenuItem(
                      value: 'doctor:D1',
                      child: Text('BS. Mai · Cá nhân'),
                    ),
                    DropdownMenuItem(
                      value: 'doctor:D2',
                      child: Text('BS. An · Cá nhân'),
                    ),
                    DropdownMenuItem(
                      value: 'doctor:D3',
                      child: Text('BS. Lan · Cá nhân'),
                    ),
                  ],
                  onChanged: c.sending
                      ? null
                      : (v) {
                          tab = 0;
                          finance.select(v!);
                        },
                ),
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 12,
                children: [
                  TextButton.icon(
                    onPressed: changeMonth,
                    icon: const Icon(Icons.calendar_month_outlined),
                    label: Text('Kỳ ${c.month}'),
                  ),
                  if (data != null)
                    Text(
                      _statusLabels[data['period']['status']]!,
                      style: const TextStyle(fontSize: 12),
                    ),
                ],
              ),
              if (c.error.isNotEmpty)
                card([
                  Text(
                    c.error,
                    style: const TextStyle(color: Colors.deepOrange),
                  ),
                  TextButton(
                    onPressed: () => finance.refresh(),
                    child: const Text('Thử lại'),
                  ),
                ]),
              if (data == null && c.error.isEmpty)
                const Center(child: CircularProgressIndicator()),
              if (data != null) ...content(data),
            ],
          ),
        ),
      ),
      bottomNavigationBar: PemaModernBottomNav(
        selectedIndex: tab,
        onDestinationSelected: (v) => setState(() => tab = v),
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            label: 'Tổng quan',
          ),
          const NavigationDestination(
            icon: Icon(Icons.receipt_long_outlined),
            label: 'Thủ thuật',
          ),
          const NavigationDestination(
            icon: Icon(Icons.payments_outlined),
            label: 'Thu tiền',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: c.unread > 0,
              label: Text('${c.unread}'),
              child: const Icon(Icons.notifications_outlined),
            ),
            label: 'Thông báo',
          ),
        ],
      ),
      floatingActionButton:
          tab == 1 && c.role != 'doctor' && data?['period']['status'] == 'open'
          ? FloatingActionButton.extended(
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => ProcedureForm(patientIds: widget.patientIds),
                ),
              ),
              label: const Text('Ghi lượt'),
              icon: const Icon(Icons.add),
            )
          : null,
    );
  }

  List<Widget> content(Map<String, dynamic> d) {
    final summary = d['summary'] as Map;
    final rows = d['rows'] as List;
    final private = c.role == 'doctor';
    if (tab == 0)
      return [
        Container(
          padding: const EdgeInsets.all(22),
          margin: const EdgeInsets.only(bottom: 18),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF083A6E), Color(0xFF0B4F94)],
            ),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                private ? 'DOANH SỐ CỦA TÔI' : 'DOANH SỐ THỰC HIỆN',
                style: const TextStyle(color: Color(0xFFB8DEF5), fontSize: 11),
              ),
              const SizedBox(height: 12),
              Text(
                money(summary['revenue']),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Ghi nhận theo lượt hoàn tất',
                style: TextStyle(color: Colors.white70),
              ),
            ],
          ),
        ),
        card([
          title('Dòng tiền & đối soát'),
          if (!private) ...[
            line('Thực thu trong tháng', money(summary['collected'])),
            line('Công nợ hiện tại', money(summary['debt'])),
          ],
          line('Tiền thủ thuật đã duyệt', money(summary['fee'])),
          line('Tiền chờ duyệt', money(summary['pending'])),
          const Text(
            'Tiền thủ thuật không phải lợi nhuận. Công nợ là toàn bộ số còn phải thu.',
            style: TextStyle(fontSize: 12, color: Color(0xFF5D7184)),
          ),
        ]),
        if (!private)
          card([
            title('Đội ngũ'),
            for (final doctor in d['doctors'])
              line(
                doctor['name'],
                money(
                  rows
                      .where(
                        (r) =>
                            r['doctor'] == doctor['id'] &&
                            r['status'] != 'void',
                      )
                      .fold<num>(0, (a, r) => a + r['revenue']),
                ),
              ),
          ]),
        if (!private)
          OutlinedButton.icon(
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute<void>(builder: (_) => const RateScreen()),
            ),
            icon: const Icon(Icons.tune),
            label: const Text('Chính sách tỷ lệ thủ thuật'),
          ),
      ];
    if (tab == 1)
      return [
        title('Từng lượt, từng người thực hiện'),
        const Text(
          'Tỷ lệ lưu theo lượt; kế toán đối soát trước khi chốt.',
          style: TextStyle(fontSize: 12),
        ),
        const SizedBox(height: 12),
        if (rows.isEmpty) card([const Text('Chưa có lượt trong kỳ này.')]),
        for (final r in rows)
          card([
            title(r['service']),
            Text(
              '${r['date']} · ${r['patient']} · ${d['doctors'].firstWhere((x) => x['id'] == r['doctor'])['name']}',
            ),
            line('Doanh số phân bổ', money(r['revenue'])),
            line('${money(r['base'])} × ${r['rate'] / 100}%', money(r['fee'])),
            Text(_statusLabels[r['status']]!),
            if (!private &&
                d['period']['status'] == 'open' &&
                r['status'] != 'void')
              Wrap(
                spacing: 8,
                children: [
                  if (r['status'] == 'pending')
                    TextButton(
                      onPressed: c.sending
                          ? null
                          : () => run('approve', {'id': r['id']}),
                      child: const Text('Duyệt'),
                    ),
                  TextButton(
                    onPressed: c.sending
                        ? null
                        : () async {
                            final reason = await ask('Lý do hủy');
                            if (reason != null)
                              await run('void', {
                                'id': r['id'],
                                'reason': reason,
                              });
                          },
                    child: const Text('Hủy lượt'),
                  ),
                ],
              ),
          ]),
        if (!private && d['period']['status'] == 'open')
          OutlinedButton(
            onPressed: c.sending
                ? null
                : () async {
                    final result = await ask('Gõ CHOT để khóa kỳ ${c.month}');
                    if (result == 'CHOT')
                      await run('close', {'month': c.month});
                  },
            child: const Text('Chốt tháng đã kết thúc'),
          ),
        if (!private && d['period']['status'] == 'closed')
          OutlinedButton(
            onPressed: c.sending
                ? null
                : () async {
                    final ref = await ask('Mã chứng từ chi');
                    if (ref != null)
                      await run('paid', {'month': c.month, 'reference': ref});
                  },
            child: const Text('Xác nhận đã chi'),
          ),
        const SizedBox(height: 70),
      ];
    if (tab == 2) {
      if (private)
        return [
          card([
            const Text('Bác sĩ chỉ xem doanh số và tiền thủ thuật của mình.'),
          ]),
        ];
      final invoices = (d['invoices'] as List).where(
        (i) => i['received'] < i['amount'] && i['source'] == 'finance',
      );
      return [
        title('Khoản còn phải thu'),
        const Text(
          'Thu ngân web cũ đồng bộ riêng. Chỉ thu hóa đơn tài chính tại đây.',
          style: TextStyle(fontSize: 12),
        ),
        const SizedBox(height: 12),
        for (final i in invoices)
          card([
            title(i['patient']),
            Text(i['id'], maxLines: 1, overflow: TextOverflow.ellipsis),
            line('Còn lại', money(i['amount'] - i['received'])),
            FilledButton(
              onPressed: c.sending
                  ? null
                  : () async {
                      final text = await ask('Số tiền mặt thu (VND)');
                      final amount = int.tryParse(text ?? '');
                      if (amount == null) return;
                      final ok = await finance.command('payment', {
                        'id': 'APP-$paymentKey',
                        'invoice': i['id'],
                        'amount': amount,
                        'method': 'Tiền mặt',
                      });
                      if (ok) {
                        paymentKey = DateTime.now().microsecondsSinceEpoch
                            .toString();
                        if (mounted)
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text(
                                'Đã thu và thông báo chủ phòng khám',
                              ),
                            ),
                          );
                      }
                    },
              child: const Text('Thu tiền mặt'),
            ),
          ]),
        if (invoices.isEmpty) card([const Text('Không còn hóa đơn chờ thu.')]),
      ];
    }
    return [
      title('Thanh toán mới'),
      if (c.role != 'owner')
        card([const Text('Inbox này dành cho chủ phòng khám.')])
      else ...[
        if ((d['notifications'] as List).isEmpty)
          card([
            const Text(
              'Thanh toán thành công sẽ xuất hiện ở đây khi app đang mở.',
            ),
          ]),
        for (final n in d['notifications'])
          card([
            Row(
              children: [
                const Icon(Icons.payments_outlined, color: Color(0xFF0B4F94)),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    n['title'],
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(n['body']),
            Text(
              n['at'].substring(0, 16).replaceAll('T', ' '),
              style: const TextStyle(fontSize: 11),
            ),
            if (n['read'] == false)
              TextButton(
                onPressed: () => run('read', {'id': n['id']}),
                child: const Text('Đánh dấu đã đọc'),
              ),
          ]),
      ],
      const Text(
        'Đồng bộ khi ứng dụng đang mở; push nền chưa được cấu hình.',
        style: TextStyle(fontSize: 11, color: Color(0xFF5D7184)),
      ),
    ];
  }
}
