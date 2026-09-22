import 'package:flutter/material.dart';
import 'store.dart';

const blue = Color(0xFF0B4F94),
    navy = Color(0xFF083A6E),
    sky = Color(0xFF3CAAE5),
    ink = Color(0xFF17324D),
    muted = Color(0xFF5D7184),
    paper = Color(0xFFF4F8FB);
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final store = DemoStore();
  await store.load();
  runApp(PemaApp(store: store));
}

class PemaApp extends StatelessWidget {
  final DemoStore store;
  const PemaApp({super.key, required this.store});
  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'Pema • Native review',
    theme: ThemeData(
      useMaterial3: true,
      fontFamily: 'BeVietnam',
      scaffoldBackgroundColor: paper,
      colorScheme: ColorScheme.fromSeed(
        seedColor: blue,
        primary: blue,
        surface: Colors.white,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: paper,
        foregroundColor: ink,
        scrolledUnderElevation: 0,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFFD9E5EE)),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      textTheme: const TextTheme(
        bodyMedium: TextStyle(color: ink, fontSize: 14, height: 1.5),
      ),
    ),
    home: Workspace(store: store),
  );
}

class Workspace extends StatefulWidget {
  final DemoStore store;
  const Workspace({super.key, required this.store});
  @override
  State<Workspace> createState() => _WorkspaceState();
}

class _WorkspaceState extends State<Workspace> {
  bool care = false;
  int index = 0;
  DemoStore get s => widget.store;
  @override
  void initState() {
    super.initState();
    s.addListener(refresh);
  }

  void refresh() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    s.removeListener(refresh);
    super.dispose();
  }

  void open(String route) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => Detail(store: s, route: route, care: care),
      ),
    );
  }

  Widget action(String name, IconData icon, String route) => Expanded(
    child: Padding(
      padding: const EdgeInsets.all(4),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => open(route),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 4),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(18),
          ),
          child: Column(
            children: [
              Icon(icon, color: blue),
              const SizedBox(height: 9),
              Text(
                name,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
  @override
  Widget build(BuildContext context) {
    final labels = care
        ? ['Trang chủ', 'Hành trình', 'Tin nhắn', 'Hồ sơ']
        : ['Hôm nay', 'Lịch hẹn', 'Hồ sơ', 'Theo dõi', 'Thêm'];
    final icons = care
        ? [
            Icons.home_outlined,
            Icons.route_outlined,
            Icons.chat_bubble_outline,
            Icons.person_outline,
          ]
        : [
            Icons.space_dashboard_outlined,
            Icons.calendar_month_outlined,
            Icons.people_outline,
            Icons.inbox_outlined,
            Icons.grid_view_outlined,
          ];
    return Scaffold(
      appBar: AppBar(
        title: Image.asset('assets/pema-logo.png', width: 94),
        actions: [
          TextButton.icon(
            onPressed: () => showModalBottomSheet(
              context: context,
              showDragHandle: true,
              builder: (ctx) => SafeArea(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Duyệt không gian làm việc',
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const Text(
                        'Dữ liệu mẫu • chưa phải đăng nhập/phân quyền',
                      ),
                      for (final mode in [false, true])
                        ListTile(
                          leading: Icon(
                            mode
                                ? Icons.favorite_outline
                                : Icons.medical_services_outlined,
                          ),
                          title: Text(
                            mode
                                ? 'Pema Care · Người bệnh'
                                : 'Pema Clinic · Phòng khám',
                          ),
                          trailing: care == mode
                              ? const Icon(Icons.check, color: blue)
                              : null,
                          onTap: () {
                            setState(() {
                              care = mode;
                              index = 0;
                            });
                            Navigator.pop(ctx);
                          },
                        ),
                    ],
                  ),
                ),
              ),
            ),
            icon: const Icon(Icons.swap_horiz, size: 18),
            label: Text(care ? 'Care' : 'Clinic'),
          ),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
              children: body(),
            ),
          ),
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) => setState(() => index = i),
        backgroundColor: Colors.white,
        indicatorColor: const Color(0xFFE8F4FB),
        destinations: List.generate(
          labels.length,
          (i) => NavigationDestination(icon: Icon(icons[i]), label: labels[i]),
        ),
      ),
    );
  }

  List<Widget> body() {
    if (care) {
      if (index == 1)
        return [
          heading('Hành trình của bạn', 'Mỗi bước chăm sóc đều được ghi nhận'),
          hero(
            'Phục hồi & chăm sóc da',
            '${s.sessions}/5 buổi đã hoàn tất',
            Icons.spa_outlined,
          ),
          ...[
            'Kế hoạch điều trị',
            'Ảnh tiến triển',
            'Chăm sóc tại nhà',
            'Đơn thuốc & tư vấn',
          ].map(
            (x) => tile(
              x,
              'Xem chi tiết và hướng dẫn',
              Icons.chevron_right,
              () => open(x),
            ),
          ),
        ];
      if (index == 2)
        return [
          heading('Tin nhắn', 'Đội ngũ Pema luôn đồng hành'),
          notice(
            'Nếu có dấu hiệu bất thường nặng, hãy liên hệ trực tiếp. Tin nhắn không phải kênh cấp cứu.',
          ),
          ...s.updates.map(
            (x) => tile('Bạn', x, Icons.chat_bubble_outline, null),
          ),
          if (s.response.isNotEmpty)
            tile('Đội ngũ Pema', s.response, Icons.verified_outlined, null),
          primary('Gửi cập nhật', () => open('Gửi cập nhật')),
        ];
      if (index == 3)
        return [
          heading(s.name, '${s.patientId} · Hồ sơ minh họa'),
          ...[
            'Đơn thuốc & tư vấn',
            'Hóa đơn',
            'Quyền riêng tư',
            'Hướng dẫn',
          ].map(
            (x) => tile(
              x,
              'Thông tin của bạn',
              Icons.chevron_right,
              () => open(x),
            ),
          ),
        ];
      return [
        heading('Chào Linh,', 'Hôm nay, dành chút thời gian cho làn da'),
        hero(
          'Chăm sóc nhẹ nhàng.\nĐồng hành mỗi ngày.',
          'Liệu trình phục hồi · Buổi ${s.sessions}/5',
          Icons.spa_outlined,
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            action('Chăm sóc', Icons.favorite_outline, 'Chăm sóc tại nhà'),
            action('Gửi cập nhật', Icons.add_a_photo_outlined, 'Gửi cập nhật'),
            action(
              'Đơn đã duyệt',
              Icons.receipt_long_outlined,
              'Đơn thuốc & tư vấn',
            ),
          ],
        ),
        section('Lịch hẹn tiếp theo'),
        tile(
          '${s.appointment} · ${s.day}',
          'BS. Tâm · Khám da liễu',
          Icons.calendar_today_outlined,
          () => open('Lịch của tôi'),
        ),
        section('Việc cần làm'),
        tile(
          s.acknowledged ? 'Đã đọc hướng dẫn' : 'Đọc hướng dẫn sau điều trị',
          'Bác sĩ đã gửi hướng dẫn cho bạn',
          s.acknowledged ? Icons.check_circle_outline : Icons.favorite_outline,
          () => open('Chăm sóc tại nhà'),
        ),
      ];
    }
    if (index == 1)
      return [
        heading('Điều phối lịch', 'Thứ Ba, 22 tháng 9'),
        const WeekStrip(),
        tile(
          'BS. Tâm · Phòng khám 01',
          'Ca sáng 08:00–12:00',
          Icons.tune,
          () => open('Bác sĩ & phòng'),
        ),
        for (final time in ['09:00', s.appointment, '14:00'])
          tile(
            time,
            time == s.appointment ? '${s.name} · Tái khám' : 'Khung giờ trống',
            Icons.schedule,
            () => open('Chi tiết lịch'),
          ),
        primary('Đặt / dời lịch', () => open('Đặt lịch')),
      ];
    if (index == 2)
      return [
        heading('Hồ sơ người bệnh', '36 hồ sơ tổng hợp · Patient 360'),
        PatientSearch(store: s, onOpen: () => open('Patient 360')),
      ];
    if (index == 3)
      return [
        heading('Theo dõi', 'Ưu tiên phản hồi và bàn giao'),
        notice(
          '${s.updates.length} cập nhật · ${s.response.isEmpty ? '1 cần phản hồi' : 'Đã phản hồi'}',
        ),
        ...s.updates.map(
          (x) => tile(
            s.name,
            x,
            Icons.chat_bubble_outline,
            () => open('Phản hồi'),
          ),
        ),
        tile(
          'Cần gọi lại',
          'Hồ sơ mẫu · triệu chứng tăng',
          Icons.priority_high,
          () => open('Phản hồi'),
        ),
      ];
    if (index == 4)
      return [
        heading('Không gian làm việc', 'Nghiệp vụ theo đúng hành trình Pema'),
        ...[
          'Lên đơn nhanh',
          'Thu ngân',
          'Dịch vụ',
          'Bác sĩ & phòng',
          'Ảnh tiến triển',
          'Ask Pema',
          'Hướng dẫn',
        ].map(
          (x) => tile(
            x,
            'Mở ${x.toLowerCase()}',
            Icons.chevron_right,
            () => open(x),
          ),
        ),
        notice(
          'Template tương tác • dữ liệu mẫu trong phiên. Chuyển Clinic/Care ở góc trên để duyệt bàn giao.',
        ),
      ];
    return [
      heading('Chào buổi sáng, BS. Tâm', 'Thứ Ba · 22 tháng 09, 2026'),
      hero(
        'Một ngày chăm sóc\ntrọn vẹn hơn.',
        '${s.updates.length} phản hồi cần theo dõi',
        Icons.wb_sunny_outlined,
      ),
      const SizedBox(height: 16),
      Row(
        children: [
          metric('12', 'Lịch hôm nay'),
          const SizedBox(width: 12),
          metric(s.checkedIn ? '04' : '03', 'Đang chờ'),
        ],
      ),
      section('Bắt đầu nhanh'),
      Row(
        children: [
          action('Lên đơn', Icons.note_add_outlined, 'Lên đơn nhanh'),
          action('Đặt lịch', Icons.calendar_month_outlined, 'Đặt lịch'),
          action('Thu ngân', Icons.payments_outlined, 'Thu ngân'),
        ],
      ),
      section('Lượt khám tiếp theo'),
      tile(
        s.name,
        '${s.appointment} · ${s.checkedIn ? 'Đã check-in' : 'Chờ tiếp nhận'} · Tái khám',
        Icons.person_outline,
        () => open('Patient 360'),
      ),
      tile(
        'Theo dõi sau điều trị',
        'Xem ảnh và phản hồi từ người bệnh',
        Icons.inbox_outlined,
        () => setState(() => index = 3),
      ),
    ];
  }
}

Widget heading(String title, String sub) => Padding(
  padding: const EdgeInsets.only(bottom: 20),
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        title,
        style: const TextStyle(
          fontSize: 25,
          fontWeight: FontWeight.w700,
          color: navy,
        ),
      ),
      const SizedBox(height: 6),
      Text(sub, style: const TextStyle(color: muted, fontSize: 13)),
    ],
  ),
);
Widget section(String title) => Padding(
  padding: const EdgeInsets.only(top: 24, bottom: 12),
  child: Text(
    title,
    style: const TextStyle(
      fontSize: 17,
      fontWeight: FontWeight.w700,
      color: ink,
    ),
  ),
);
Widget hero(String title, String sub, IconData icon) => Container(
  clipBehavior: Clip.antiAlias,
  decoration: BoxDecoration(
    borderRadius: BorderRadius.circular(24),
    gradient: const LinearGradient(
      colors: [navy, blue],
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
    ),
  ),
  child: Stack(
    children: [
      Positioned(
        right: -20,
        top: -22,
        child: Icon(
          icon,
          size: 170,
          color: Colors.white.withValues(alpha: .09),
        ),
      ),
      Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'PEMA • CHĂM SÓC LIÊN TỤC',
              style: TextStyle(
                color: Color(0xFFB8DEF5),
                fontSize: 10,
                letterSpacing: 1.4,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 24,
                height: 1.3,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              sub,
              style: const TextStyle(color: Color(0xFFD7E9F5), fontSize: 12),
            ),
          ],
        ),
      ),
    ],
  ),
);
Widget metric(String value, String label) => Expanded(
  child: Container(
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: const TextStyle(
            fontSize: 28,
            color: blue,
            fontWeight: FontWeight.w700,
          ),
        ),
        Text(label, style: const TextStyle(color: muted, fontSize: 12)),
      ],
    ),
  ),
);
Widget tile(String title, String sub, IconData icon, VoidCallback? tap) => Card(
  elevation: 0,
  margin: const EdgeInsets.only(bottom: 10),
  color: Colors.white,
  shape: RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(18),
    side: const BorderSide(color: Color(0xFFE3ECF3)),
  ),
  child: ListTile(
    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
    leading: CircleAvatar(
      backgroundColor: const Color(0xFFE8F4FB),
      child: Icon(icon, color: blue, size: 21),
    ),
    title: Text(
      title,
      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
    ),
    subtitle: Text(sub, style: const TextStyle(fontSize: 12, color: muted)),
    trailing: tap == null
        ? null
        : const Icon(Icons.chevron_right, size: 18, color: muted),
    onTap: tap,
  ),
);
Widget notice(String text) => Container(
  margin: const EdgeInsets.only(bottom: 16),
  padding: const EdgeInsets.all(16),
  decoration: BoxDecoration(
    color: const Color(0xFFE8F4FB),
    borderRadius: BorderRadius.circular(14),
  ),
  child: Text(text, style: const TextStyle(fontSize: 12, color: navy)),
);
Widget primary(String text, VoidCallback? tap) => Padding(
  padding: const EdgeInsets.symmetric(vertical: 8),
  child: FilledButton(onPressed: tap, child: Text(text)),
);

class WeekStrip extends StatelessWidget {
  const WeekStrip({super.key});
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 20),
    child: Row(
      children: List.generate(
        7,
        (i) => Expanded(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 2),
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              color: i == 1 ? blue : Colors.white,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              children: [
                Text(
                  ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'][i],
                  style: TextStyle(
                    fontSize: 10,
                    color: i == 1 ? Colors.white : muted,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '${21 + i}',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: i == 1 ? Colors.white : ink,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class PatientSearch extends StatefulWidget {
  final DemoStore store;
  final VoidCallback onOpen;
  const PatientSearch({super.key, required this.store, required this.onOpen});
  @override
  State<PatientSearch> createState() => _PatientSearchState();
}

class _PatientSearchState extends State<PatientSearch> {
  String query = '';
  @override
  Widget build(BuildContext context) => Column(
    children: [
      TextField(
        decoration: const InputDecoration(
          prefixIcon: Icon(Icons.search),
          hintText: 'Tìm tên hoặc mã hồ sơ',
        ),
        onChanged: (v) => setState(() => query = v.toLowerCase()),
      ),
      const SizedBox(height: 16),
      for (int i = 0; i < widget.store.patients.length; i++)
        if (widget.store.patients[i].toLowerCase().contains(query) ||
            'p${(i + 1).toString().padLeft(3, '0')}'.contains(query))
          tile(
            widget.store.patients[i],
            'P${(i + 1).toString().padLeft(3, '0')} · Đang điều trị',
            Icons.person_outline,
            () {
              widget.store.change(() => widget.store.selected = i);
              widget.onOpen();
            },
          ),
    ],
  );
}

class Detail extends StatefulWidget {
  final DemoStore store;
  final String route;
  final bool care;
  const Detail({
    super.key,
    required this.store,
    required this.route,
    this.care = false,
  });
  @override
  State<Detail> createState() => _DetailState();
}

class _DetailState extends State<Detail> {
  DemoStore get s => widget.store;
  final text = TextEditingController();
  bool consent = false, photo = false;
  String filter = '';
  @override
  void initState() {
    super.initState();
    s.addListener(refresh);
  }

  void refresh() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    s.removeListener(refresh);
    text.dispose();
    super.dispose();
  }

  void open(String route) => Navigator.push(
    context,
    MaterialPageRoute(
      builder: (_) => Detail(store: s, route: route, care: widget.care),
    ),
  );
  void toast(String message) => ScaffoldMessenger.of(
    context,
  ).showSnackBar(SnackBar(content: Text(message)));
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        widget.route,
        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
      ),
    ),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: content(),
          ),
        ),
      ),
    ),
  );
  List<Widget> content() {
    switch (widget.route) {
      case 'Patient 360':
        return [
          heading(s.name, '${s.patientId} · 32 tuổi · BS. Tâm'),
          notice('Da nhạy cảm • Cần đọc tiền sử trước khi kê đơn'),
          Row(
            children: [
              metric('${s.sessions}/5', 'Buổi điều trị'),
              const SizedBox(width: 12),
              metric(s.appointment, 'Lịch tiếp theo'),
            ],
          ),
          section('Hồ sơ xuyên suốt'),
          ...[
            'Tư vấn',
            'Kế hoạch điều trị',
            'Buổi điều trị',
            'Ảnh tiến triển',
            'Lên đơn nhanh',
            'Đơn thuốc & tư vấn',
            'Hóa đơn',
          ].map(
            (x) =>
                tile(x, 'Xem và cập nhật', Icons.chevron_right, () => open(x)),
          ),
          primary(
            s.checkedIn ? 'Đã check-in' : 'Check-in người bệnh',
            s.checkedIn ? null : () => s.change(() => s.checkedIn = true),
          ),
        ];
      case 'Lên đơn nhanh':
        return [
          notice(
            '${s.name} · ${s.patientId}\n115 sản phẩm từ catalog web. Đơn nháp chưa gửi cho người bệnh.',
          ),
          TextField(
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Tìm mã hoặc tên sản phẩm',
            ),
            onChanged: (v) => setState(() => filter = v.toLowerCase()),
          ),
          const SizedBox(height: 12),
          primary(
            'Xem đơn · ${s.cart.length} sản phẩm · ${money(s.total)}',
            s.cart.isEmpty ? null : () => open('Kiểm tra đơn'),
          ),
          for (final p
              in s.products
                  .where(
                    (p) => '${p['code']} ${p['name']}'.toLowerCase().contains(
                      filter,
                    ),
                  )
                  .take(20))
            tile(
              p['name'],
              '${p['code']} · ${p['unit']} · ${money(p['price'])}\n${p['outputType'] == 'UNRESOLVED' ? 'Cần phân loại' : p['sourceType']}',
              Icons.add,
              () {
                s.add(p);
                toast('Đã thêm ${p['code']}');
              },
            ),
        ];
      case 'Kiểm tra đơn':
        return [
          heading(
            'Kiểm tra trước khi duyệt',
            '${s.cart.length} dòng · ${money(s.total)}',
          ),
          ...s.cart.map(
            (p) => Card(
              elevation: 0,
              color: Colors.white,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      p['name'],
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    Row(
                      children: [
                        IconButton(
                          tooltip: 'Giảm số lượng',
                          onPressed: () => s.change(() {
                            if (p['quantity'] > 1) p['quantity']--;
                          }),
                          icon: const Icon(Icons.remove_circle_outline),
                        ),
                        Text('${p['quantity']} ${p['unit']}'),
                        IconButton(
                          tooltip: 'Tăng số lượng',
                          onPressed: () => s.change(() => p['quantity']++),
                          icon: const Icon(Icons.add_circle_outline),
                        ),
                        const Spacer(),
                        IconButton(
                          tooltip: 'Xóa dòng',
                          onPressed: () => s.change(() => s.cart.remove(p)),
                          icon: const Icon(Icons.delete_outline),
                        ),
                      ],
                    ),
                    DropdownButtonFormField<String>(
                      initialValue: p['route'],
                      isExpanded: true,
                      items: const [
                        DropdownMenuItem(
                          value: 'UNRESOLVED',
                          child: Text('Cần phân loại'),
                        ),
                        DropdownMenuItem(
                          value: 'PRESCRIPTION',
                          child: Text('Đơn thuốc'),
                        ),
                        DropdownMenuItem(
                          value: 'CONSULTATION',
                          child: Text('Phiếu tư vấn'),
                        ),
                      ],
                      onChanged: (v) => s.change(() => p['route'] = v),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      initialValue: p['usage'],
                      decoration: const InputDecoration(
                        labelText: 'Cách dùng / hướng dẫn',
                      ),
                      onChanged: (v) => s.change(() => p['usage'] = v),
                    ),
                  ],
                ),
              ),
            ),
          ),
          notice(
            'Tài khoản bác sĩ mô phỏng. Chỉ duyệt khi đã phân loại và nhập hướng dẫn cho mọi dòng.',
          ),
          primary(
            'Lưu nháp',
            s.cart.isEmpty
                ? null
                : () {
                    s.saveOrder(false);
                    open('Đơn thuốc & tư vấn');
                  },
          ),
          primary(
            'Bác sĩ duyệt đơn',
            s.ready
                ? () {
                    s.saveOrder(true);
                    open('Đơn thuốc & tư vấn');
                  }
                : null,
          ),
        ];
      case 'Đơn thuốc & tư vấn':
        return [
          notice(
            widget.care
                ? 'Chỉ hiển thị nội dung đã được bác sĩ duyệt.'
                : 'Nháp → bác sĩ duyệt → người bệnh xem. In không đồng nghĩa đã cấp thuốc.',
          ),
          if (s.myOrders
              .where((o) => !widget.care || o['approved'] == true)
              .isEmpty)
            tile(
              'Chưa có đơn${widget.care ? ' đã duyệt' : ''}',
              'Đơn mới sẽ xuất hiện tại đây',
              Icons.receipt_long_outlined,
              null,
            ),
          for (final o in s.myOrders.where(
            (o) => !widget.care || o['approved'] == true,
          )) ...[
            section('${o['id']} · ${o['approved'] ? 'Đã duyệt' : 'Nháp'}'),
            for (final route in ['PRESCRIPTION', 'CONSULTATION']) ...[
              Text(
                route == 'PRESCRIPTION' ? 'Đơn thuốc' : 'Phiếu tư vấn',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              for (final p in (o['items'] as List).where(
                (p) => p['route'] == route,
              ))
                tile(
                  p['name'],
                  '${p['quantity']} ${p['unit']} · ${p['usage']}',
                  Icons.medication_outlined,
                  null,
                ),
            ],
            if (!widget.care && o['approved'] == false)
              primary('Sửa và duyệt bản nháp', () {
                s.edit(o);
                open('Kiểm tra đơn');
              }),
            if (!widget.care)
              primary('Xem bố cục hai phiếu A5', () => open('Phiếu A5')),
          ],
        ];
      case 'Phiếu A5':
        return [
          notice(
            'Bản duyệt bố cục trên điện thoại. In / chia sẻ PDF native sẽ nối sau khi duyệt template.',
          ),
          for (final kind in ['ĐƠN THUỐC', 'PHIẾU TƯ VẤN'])
            Card(
              color: Colors.white,
              elevation: 0,
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Image.asset('assets/pema-logo.png', width: 90),
                    section(kind),
                    Text(s.name),
                    const Divider(),
                    for (final o in s.myOrders.where(
                      (o) => o['approved'] == true,
                    ))
                      for (final p in (o['items'] as List).where(
                        (p) =>
                            p['route'] ==
                            (kind == 'ĐƠN THUỐC'
                                ? 'PRESCRIPTION'
                                : 'CONSULTATION'),
                      ))
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: Text(
                            '${p['name']}\n${p['quantity']} ${p['unit']} · ${p['usage']}',
                          ),
                        ),
                    const Divider(),
                    Text(
                      kind == 'ĐƠN THUỐC'
                          ? 'Mang theo đơn này · Kiểm tra thuốc\nBác sĩ khám'
                          : 'Mang theo phiếu này · Kiểm tra sản phẩm\nBác sĩ tư vấn',
                    ),
                    const SizedBox(height: 32),
                    const Text('BS. Tâm'),
                  ],
                ),
              ),
            ),
        ];
      case 'Đặt lịch':
        return [
          heading(s.name, 'Chọn ngày và giờ trước khi xác nhận'),
          const WeekStrip(),
          tile(
            s.day,
            'Chạm để đổi ngày',
            Icons.calendar_today_outlined,
            () async {
              final d = await showDatePicker(
                context: context,
                initialDate: DateTime(2026, 9, 22),
                firstDate: DateTime(2026, 9, 22),
                lastDate: DateTime(2027),
              );
              if (d != null)
                s.change(() => s.day = '${d.day}/${d.month}/${d.year}');
            },
          ),
          notice(
            'BS. Tâm · Khám da liễu · 30 phút\n09:00 đã có lịch, không thể chọn.',
          ),
          Wrap(
            spacing: 8,
            children: ['09:00', '10:30', '11:00', '14:00', '15:30']
                .map(
                  (t) => ChoiceChip(
                    label: Text(t),
                    selected: s.appointment == t,
                    onSelected: t == '09:00'
                        ? null
                        : (_) => s.change(() => s.appointment = t),
                  ),
                )
                .toList(),
          ),
          primary('Xác nhận lịch', () {
            s.change(() => s.confirmed = true);
            toast('Đã lưu lịch ${s.appointment} · ${s.day}');
            Navigator.pop(context);
          }),
        ];
      case 'Chi tiết lịch':
      case 'Lịch của tôi':
        return [
          hero(
            '${s.appointment} · ${s.day}',
            'BS. Tâm · Khám da liễu',
            Icons.calendar_month_outlined,
          ),
          section(s.name),
          notice('Tái khám & đánh giá · 30 phút'),
          primary(
            s.confirmed ? 'Đã xác nhận' : 'Xác nhận tham dự',
            s.confirmed ? null : () => s.change(() => s.confirmed = true),
          ),
          if (!widget.care) primary('Dời lịch', () => open('Đặt lịch')),
          if (!widget.care)
            primary('Mở Patient 360', () => open('Patient 360')),
        ];
      case 'Tư vấn':
        return [
          notice('Ghi chú chuyên môn là bản nháp, cần bác sĩ xem lại.'),
          TextField(
            controller: text,
            maxLines: 6,
            decoration: InputDecoration(
              labelText: 'Ghi chú tư vấn',
              hintText: s.note,
            ),
          ),
          primary('Lưu ghi chú nháp', () {
            s.change(() => s.note = text.text);
            toast('Đã lưu ghi chú');
          }),
          primary('Xem tóm tắt AI', () => open('Ask Pema')),
        ];
      case 'Kế hoạch điều trị':
        return [
          hero(
            'Phục hồi & chăm sóc da',
            '${s.sessions}/5 buổi · BS. Tâm',
            Icons.route_outlined,
          ),
          section('Các mốc chăm sóc'),
          for (int i = 1; i <= 5; i++)
            tile(
              'Buổi $i',
              i <= s.sessions ? 'Đã hoàn tất' : 'Chờ đánh giá / thực hiện',
              i <= s.sessions
                  ? Icons.check_circle_outline
                  : Icons.circle_outlined,
              null,
            ),
          primary('Xem chăm sóc tại nhà', () => open('Chăm sóc tại nhà')),
        ];
      case 'Buổi điều trị':
        return [
          notice('Buổi ${s.sessions + 1}/5 · BS. Tâm'),
          TextField(
            controller: text,
            maxLines: 4,
            decoration: const InputDecoration(
              labelText: 'Ghi nhận buổi điều trị *',
            ),
            onChanged: (_) => setState(() {}),
          ),
          CheckboxListTile(
            value: consent,
            onChanged: (v) => setState(() => consent = v!),
            title: const Text('Đã kiểm tra và bàn giao aftercare'),
          ),
          primary(
            'Hoàn tất buổi',
            consent && text.text.trim().isNotEmpty && s.sessions < 5
                ? () {
                    s.change(() => s.sessions++);
                    toast('Đã lưu buổi và cập nhật hành trình');
                    Navigator.pop(context);
                  }
                : null,
          ),
        ];
      case 'Chăm sóc tại nhà':
        return [
          heading(
            'Nhẹ nhàng với làn da',
            'Hướng dẫn mẫu đã được bác sĩ kiểm tra',
          ),
          ...[
            'Làm sạch dịu nhẹ',
            'Dưỡng ẩm theo hướng dẫn',
            'Bảo vệ da khỏi ánh nắng',
          ].map(
            (x) => tile(
              x,
              'Thực hiện theo hướng dẫn cá nhân đã duyệt.',
              Icons.favorite_outline,
              null,
            ),
          ),
          primary(
            s.acknowledged ? 'Đã xác nhận đã đọc' : 'Tôi đã đọc hướng dẫn',
            s.acknowledged ? null : () => s.change(() => s.acknowledged = true),
          ),
          primary('Gửi cập nhật cho Pema', () => open('Gửi cập nhật')),
        ];
      case 'Gửi cập nhật':
        return [
          notice('Cập nhật sẽ vào hàng chờ để đội ngũ Pema xem.'),
          TextField(
            controller: text,
            maxLines: 5,
            decoration: const InputDecoration(
              labelText: 'Hôm nay da bạn thế nào?',
            ),
            onChanged: (_) => setState(() {}),
          ),
          primary(
            photo ? 'Đã chọn ảnh mẫu' : 'Đính kèm ảnh minh họa',
            () => setState(() => photo = !photo),
          ),
          if (photo)
            notice('Ảnh mẫu dùng duyệt UI • camera native chưa kết nối'),
          if (photo)
            CheckboxListTile(
              value: consent,
              onChanged: (v) => setState(() => consent = v!),
              title: const Text('Tôi đồng ý chia sẻ ảnh để chăm sóc'),
            ),
          primary(
            'Gửi cập nhật',
            text.text.trim().isNotEmpty && (!photo || consent)
                ? () {
                    s.change(() => s.updates.add(text.text));
                    toast('Đã gửi • Chờ đội ngũ xem');
                    Navigator.pop(context);
                  }
                : null,
          ),
        ];
      case 'Phản hồi':
        return [
          heading(s.name, 'Cập nhật từ Patient Mobile'),
          ...s.updates.map((x) => notice(x)),
          TextField(
            controller: text,
            maxLines: 5,
            decoration: const InputDecoration(
              labelText: 'Phản hồi đã kiểm tra',
            ),
            onChanged: (_) => setState(() {}),
          ),
          primary(
            'Duyệt và phản hồi',
            text.text.trim().isNotEmpty
                ? () {
                    s.change(() => s.response = text.text);
                    toast('Đã gửi phản hồi sang Pema Care');
                    Navigator.pop(context);
                  }
                : null,
          ),
        ];
      case 'Hóa đơn':
      case 'Thu ngân':
        final amount = s.myOrders.fold<int>(
          0,
          (n, o) => n + (o['total'] as int),
        );
        return [
          heading('Khoản cần thanh toán', s.name),
          hero(
            money(amount - s.paid),
            'Đã thu ${money(s.paid)}',
            Icons.payments_outlined,
          ),
          ...s.myOrders.map(
            (o) => tile(
              o['id'],
              money(o['total']),
              Icons.receipt_long_outlined,
              null,
            ),
          ),
          if (!widget.care)
            primary(
              'Thu đủ phần còn lại',
              amount > s.paid
                  ? () => showModalBottomSheet(
                      context: context,
                      showDragHandle: true,
                      builder: (ctx) => SafeArea(
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              heading(
                                'Xác nhận thu tiền',
                                money(amount - s.paid),
                              ),
                              notice('Giao dịch mẫu · Không kết nối ngân hàng'),
                              primary('Xác nhận tiền mặt', () {
                                s.change(() => s.paid = amount);
                                Navigator.pop(ctx);
                              }),
                            ],
                          ),
                        ),
                      ),
                    )
                  : null,
            ),
          if (!widget.care) primary('Lên đơn mới', () => open('Lên đơn nhanh')),
        ];
      case 'Dịch vụ':
        return [
          heading('Danh mục dịch vụ', 'Giá và thời lượng tham khảo như web'),
          for (final item in [
            'Tái khám & đánh giá|300.000 ₫ · 30 phút',
            'Tư vấn da liễu|500.000 ₫ · 45 phút',
            'Laser theo chỉ định|2.500.000 ₫ · 45 + 15 phút',
            'Chăm sóc theo chỉ định|1.200.000 ₫ · 45 + 15 phút',
          ])
            tile(
              item.split('|')[0],
              item.split('|')[1],
              Icons.spa_outlined,
              () => open('Đặt lịch'),
            ),
        ];
      case 'Bác sĩ & phòng':
        return [
          heading('Nguồn lực phòng khám', 'Chạm lịch để điều phối theo ca'),
          for (final name in ['BS. Tâm', 'BS. Mai', 'BS. An', 'BS. Lan'])
            tile(
              name,
              '08:00–18:00 · Nghỉ 12:00–13:00',
              Icons.medical_services_outlined,
              () => open('Đặt lịch'),
            ),
          notice(
            'Laser & thủ thuật · Bảo trì 14:00–15:00 ngày 23/09. Khóa phòng phức tạp duyệt ở web.',
          ),
        ];
      case 'Ảnh tiến triển':
        return [
          heading(
            'Theo dõi bằng hình ảnh',
            'Ảnh minh họa • không đánh giá hiệu quả tự động',
          ),
          Row(
            children: [
              for (final label in ['Trước', 'Gần nhất'])
                Expanded(
                  child: Container(
                    margin: const EdgeInsets.all(4),
                    height: 220,
                    decoration: BoxDecoration(
                      color: const Color(0xFFE8F4FB),
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(
                          Icons.face_outlined,
                          size: 76,
                          color: Color(0xFF80B3D0),
                        ),
                        Text(label),
                        const Text('Minh họa', style: TextStyle(fontSize: 11)),
                      ],
                    ),
                  ),
                ),
            ],
          ),
          notice('Chính diện · Vùng mặt · Cần cùng điều kiện ánh sáng'),
          primary('Gửi ảnh cập nhật', () => open('Gửi cập nhật')),
        ];
      case 'Ask Pema':
        return [
          hero(
            'Bối cảnh trước\nmỗi quyết định.',
            'AI mô phỏng • cần bác sĩ kiểm tra',
            Icons.auto_awesome_outlined,
          ),
          section('Tóm tắt ${s.name}'),
          notice(
            'Đã hoàn tất ${s.sessions}/5 buổi. Có ${s.updates.length} phản hồi tại nhà.\nNguồn: hành trình và cập nhật trong phiên mẫu.',
          ),
          tile(
            'Việc còn mở',
            'Xem phản hồi trước khi khám lại.',
            Icons.inbox_outlined,
            () => open('Phản hồi'),
          ),
          primary('Mở ghi chú để bác sĩ sửa', () => open('Tư vấn')),
        ];
      case 'Quyền riêng tư':
        return [
          notice('Template không sử dụng dữ liệu bệnh nhân thật.'),
          CheckboxListTile(
            value: consent,
            onChanged: (v) => setState(() => consent = v!),
            title: const Text('Đồng ý dùng ảnh trong chăm sóc'),
          ),
          const Text('Cài đặt đang được minh họa trong phiên duyệt.'),
        ];
      default:
        return [
          heading('Một hành trình, nhiều điểm nối', 'Hướng dẫn sử dụng Pema'),
          ...[
            'Tiếp nhận → lịch → Patient 360',
            'Dịch vụ → kế hoạch → buổi điều trị',
            'Đơn nháp → bác sĩ duyệt → người bệnh xem',
            'Cập nhật tại nhà → theo dõi → phản hồi',
            'Hóa đơn → thu tiền → đối soát',
          ].map(
            (x) => tile(
              x,
              'Mỗi bàn giao cần người phụ trách và bước tiếp theo.',
              Icons.route_outlined,
              null,
            ),
          ),
          notice(
            'Duyệt Clinic/Care qua nút góc trên. Thao tác mẫu lưu trong bộ nhớ, tải lại sẽ bắt đầu phiên mới.',
          ),
        ];
    }
  }
}
