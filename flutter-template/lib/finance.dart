import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const financeApi = String.fromEnvironment(
  'PEMA_FINANCE_API',
  defaultValue: 'http://127.0.0.1:4174',
);
String cash(num n) =>
    '${n.round().toString().replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+(?!\d))'), (m) => '${m[1]}.')} ₫';
String financeMonth() => DateTime.now()
    .toUtc()
    .add(const Duration(hours: 7))
    .toIso8601String()
    .substring(0, 7);
const labels = {
  'open': 'Đang đối soát',
  'closed': 'Đã chốt',
  'paid': 'Đã chi',
  'pending': 'Chờ duyệt',
  'approved': 'Đã duyệt',
  'void': 'Đã hủy',
};

class FinanceController extends ChangeNotifier with WidgetsBindingObserver {
  FinanceController({http.Client? client}) : client = client ?? http.Client();
  final http.Client client;
  String role = 'owner', doctor = 'D0', month = financeMonth(), error = '';
  Map<String, dynamic>? data;
  Timer? timer;
  int generation = 0;
  bool loading = false, sending = false, foreground = true;
  Map<String, String> get headers => {
    'Content-Type': 'application/json',
    'X-Pema-Role': role,
    'X-Pema-Doctor': doctor,
  };
  int get unread => (data?['notifications'] as List? ?? [])
      .where((n) => n['read'] == false)
      .length;
  void start() {
    WidgetsBinding.instance.addObserver(this);
    refresh();
    timer ??= Timer.periodic(const Duration(seconds: 4), (_) {
      if (foreground && !loading && !sending) refresh();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    foreground = state == AppLifecycleState.resumed;
    if (foreground) refresh();
  }

  Future<void> refresh() async {
    final token = ++generation;
    loading = true;
    try {
      final response = await client
          .get(Uri.parse('$financeApi/state?month=$month'), headers: headers)
          .timeout(const Duration(seconds: 7));
      if (token != generation) return;
      final value = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode != 200) throw Exception(value['error']);
      data = value;
      error = '';
    } catch (e) {
      if (token == generation)
        error = 'Chưa kết nối dữ liệu tài chính. Kiểm tra dịch vụ và thử lại.';
    } finally {
      if (token == generation) {
        loading = false;
        notifyListeners();
      }
    }
  }

  void select(String value) {
    final bits = value.split(':');
    role = bits[0];
    doctor = bits[1];
    data = null;
    generation++;
    notifyListeners();
    refresh();
  }

  Future<bool> command(String action, Map<String, dynamic> value) async {
    if (sending) return false;
    sending = true;
    notifyListeners();
    try {
      final response = await client
          .post(
            Uri.parse('$financeApi/command/$action'),
            headers: headers,
            body: jsonEncode(value),
          )
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200)
        throw Exception((jsonDecode(response.body) as Map)['error']);
      error = '';
      await refresh();
      return true;
    } catch (e) {
      error = e.toString().replaceFirst('Exception: ', '');
      notifyListeners();
      return false;
    } finally {
      sending = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    generation++;
    timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    client.close();
    super.dispose();
  }
}

class FinanceScreen extends StatefulWidget {
  const FinanceScreen({
    super.key,
    required this.controller,
    this.initialTab = 0,
  });
  final FinanceController controller;
  final int initialTab;
  @override
  State<FinanceScreen> createState() => _FinanceScreenState();
}

class _FinanceScreenState extends State<FinanceScreen> {
  FinanceController get c => widget.controller;
  late int tab;
  String paymentKey = DateTime.now().microsecondsSinceEpoch.toString();
  @override
  void initState() {
    super.initState();
    tab = widget.initialTab;
    c.addListener(changed);
    c.refresh();
  }

  void changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    c.removeListener(changed);
    super.dispose();
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
    final ok = await c.command(action, d);
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
      c.month = picked.toIso8601String().substring(0, 7);
      await c.refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = c.data;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tài chính Pema'),
        actions: [
          IconButton(
            onPressed: () => c.refresh(),
            icon: const Icon(Icons.refresh),
            tooltip: 'Làm mới',
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: c.refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              const Text(
                'Vai trò mẫu • dữ liệu dùng chung với web',
                style: TextStyle(fontSize: 12, color: Color(0xFF5D7184)),
              ),
              const SizedBox(height: 8),
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
                        c.select(v!);
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
                      labels[data['period']['status']]!,
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
                    onPressed: () => c.refresh(),
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
      bottomNavigationBar: NavigationBar(
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
                  builder: (_) => ProcedureForm(controller: c),
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
                cash(summary['revenue']),
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
            line('Thực thu trong tháng', cash(summary['collected'])),
            line('Công nợ hiện tại', cash(summary['debt'])),
          ],
          line('Tiền thủ thuật đã duyệt', cash(summary['fee'])),
          line('Tiền chờ duyệt', cash(summary['pending'])),
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
                cash(
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
              MaterialPageRoute<void>(
                builder: (_) => RateScreen(controller: c),
              ),
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
            line('Doanh số phân bổ', cash(r['revenue'])),
            line('${cash(r['base'])} × ${r['rate'] / 100}%', cash(r['fee'])),
            Text(labels[r['status']]!),
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
            line('Còn lại', cash(i['amount'] - i['received'])),
            FilledButton(
              onPressed: c.sending
                  ? null
                  : () async {
                      final text = await ask('Số tiền mặt thu (VND)');
                      final amount = int.tryParse(text ?? '');
                      if (amount == null) return;
                      final ok = await c.command('payment', {
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

class RateScreen extends StatefulWidget {
  const RateScreen({super.key, required this.controller});
  final FinanceController controller;
  @override
  State<RateScreen> createState() => _RateScreenState();
}

class _RateScreenState extends State<RateScreen> {
  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
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
                  if (value != null) {
                    await c.command('rate', value);
                    if (mounted) setState(() {});
                  }
                },
              ),
            ),
          if (c.error.isNotEmpty) Text(c.error),
        ],
      ),
    );
  }
}

class ProcedureForm extends StatefulWidget {
  const ProcedureForm({
    super.key,
    required this.controller,
    this.initialPatient = 'P001',
  });
  final String initialPatient;
  final FinanceController controller;
  @override
  State<ProcedureForm> createState() => _ProcedureFormState();
}

class _ProcedureFormState extends State<ProcedureForm> {
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
    final d = widget.controller.data!;
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
    final c = widget.controller, d = c.data!;
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
                List.generate(36, (i) {
                  final id = 'P${(i + 1).toString().padLeft(3, '0')}';
                  return DropdownMenuItem(value: id, child: Text(id));
                }),
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
                        final ok = await c.command('entry', {
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
