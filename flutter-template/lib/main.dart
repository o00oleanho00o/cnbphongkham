import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'care_workspace.dart';
import 'finance.dart';
import 'format.dart';
import 'state/catalog.dart';
import 'state/finance.dart';
import 'state/orders.dart';
import 'state/patients.dart';
import 'state/session.dart';
import 'widgets/pema_bottom_nav.dart';

const blue = Color(0xFF0B4F94),
    navy = Color(0xFF083A6E),
    sky = Color(0xFF3CAAE5),
    ink = Color(0xFF17324D),
    muted = Color(0xFF5D7184),
    paper = Color(0xFFF4F8FB);
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final catalog = await Catalog.load();
  runApp(
    ProviderScope(
      overrides: [
        catalogProvider.overrideWithValue(catalog),
        financeEnabledProvider.overrideWithValue(true),
      ],
      child: const PemaApp(),
    ),
  );
}

final _navigator = GlobalKey<NavigatorState>();

void pushFinance(NavigatorState navigator, WidgetRef ref, [int tab = 0]) =>
    navigator.push(
      MaterialPageRoute<void>(
        builder: (_) => FinanceScreen(
          initialTab: tab,
          lockRole: true,
          patientIds: ref.read(catalogProvider).patientIds,
        ),
      ),
    );

class PemaApp extends StatelessWidget {
  const PemaApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    navigatorKey: _navigator,
    builder: (context, child) => PaymentAlerts(child: child!),
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
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: paper,
        foregroundColor: ink,
        scrolledUnderElevation: 0,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFFCADBE8)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: blue, width: 1.5),
        ),
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
    home: const Workspace(),
  );
}

/// Lives above the Navigator: Riverpod pauses listeners on covered routes.
class PaymentAlerts extends ConsumerWidget {
  const PaymentAlerts({super.key, required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(financeEnabledProvider)) {
      ref.listen(financeProvider, (prev, next) {
        final session = ref.read(sessionProvider);
        if (session.careMode || session.staffRole != 'owner') return;
        if (prev?.data == null || next.data == null) return;
        if (next.unread <= prev!.unread) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Có thanh toán mới tại phòng khám'),
            action: SnackBarAction(
              label: 'Xem',
              onPressed: () => pushFinance(_navigator.currentState!, ref, 3),
            ),
          ),
        );
      });
    }
    return child;
  }
}

class Workspace extends ConsumerStatefulWidget {
  const Workspace({super.key});
  @override
  ConsumerState<Workspace> createState() => _WorkspaceState();
}

class _WorkspaceState extends ConsumerState<Workspace> {
  int index = 0;
  String caseGroup = 'all';
  late Session s;
  late Catalog catalog;
  late Map<String, dynamic> profile;
  late PatientState patient;
  late Map<String, PatientState> states;
  FinanceState? finance;
  bool get care => s.careMode;
  String get name => profile['name'] as String;

  @override
  void initState() {
    super.initState();
    if (ref.read(financeEnabledProvider)) {
      ref.read(financeProvider.notifier).start();
    }
  }

  void openFinance([int tab = 0]) =>
      pushFinance(Navigator.of(context), ref, tab);

  void select(int i) => ref.read(sessionProvider.notifier).select(i);

  void open(String route) {
    if (!ref.read(sessionProvider).allows(route)) return;
    Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => Detail(route: route)));
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
    s = ref.watch(sessionProvider);
    catalog = ref.watch(catalogProvider);
    profile = ref.watch(selectedProfileProvider);
    patient = ref.watch(currentPatientProvider);
    states = ref.watch(patientsProvider);
    finance = ref.watch(financeEnabledProvider)
        ? ref.watch(financeProvider)
        : null;
    final compact = !care && s.staffRole != 'owner';
    final labels = care
        ? ['Trang chủ', 'Hành trình', 'Tin nhắn', 'Hồ sơ']
        : compact
        ? ['Công việc', 'Hồ sơ mẫu']
        : ['Hôm nay', 'Lịch hẹn', 'Hồ sơ', 'Theo dõi', 'Thêm'];
    final icons = care
        ? [
            Icons.home_outlined,
            Icons.route_outlined,
            Icons.chat_bubble_outline,
            Icons.person_outline,
          ]
        : compact
        ? [Icons.work_outline, Icons.people_outline]
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
          if (!care && s.staffRole == 'owner' && finance != null)
            IconButton(
              onPressed: () => openFinance(3),
              tooltip: 'Thông báo thanh toán',
              icon: Badge(
                isLabelVisible: finance!.unread > 0,
                label: Text('${finance!.unread}'),
                child: const Icon(Icons.notifications_outlined),
              ),
            ),
          TextButton.icon(
            onPressed: () => showModalBottomSheet(
              context: context,
              showDragHandle: true,
              isScrollControlled: true,
              constraints: BoxConstraints(
                maxHeight: MediaQuery.sizeOf(context).height * .85,
              ),
              builder: (ctx) => SafeArea(
                child: SingleChildScrollView(
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
                        for (final account in [
                          ['owner', 'BS. Tâm', 'Chủ phòng khám'],
                          ['doctor', 'BS. Tâm', 'Bác sĩ điều trị'],
                          ['doctor', 'BS. Mai', 'Bác sĩ điều trị'],
                          ['care', 'Mai Anh', 'CSKH'],
                          ['accountant', 'Kế toán', 'Đối soát & thu ngân'],
                          ['patient', 'Người bệnh', 'Pema Care'],
                        ])
                          ListTile(
                            title: Text('${account[1]} · ${account[2]}'),
                            leading: Icon(
                              account[0] == 'patient'
                                  ? Icons.favorite_outline
                                  : Icons.badge_outlined,
                            ),
                            onTap: () {
                              setState(() {
                                index = 0;
                                caseGroup = 'all';
                              });
                              final session = ref.read(
                                sessionProvider.notifier,
                              );
                              if (account[0] == 'patient') {
                                session.enterCare();
                              } else {
                                session.enterStaff(account[0], account[1]);
                              }
                              final next = ref.read(sessionProvider);
                              if (ref.read(financeEnabledProvider) &&
                                  !next.careMode &&
                                  next.staffRole != 'care')
                                ref
                                    .read(financeProvider.notifier)
                                    .select(
                                      '${next.staffRole}:${next.staffDoctor == 'BS. Mai' ? 'D1' : 'D0'}',
                                    );
                              Navigator.pop(ctx);
                            },
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            icon: const Icon(Icons.swap_horiz, size: 18),
            label: Text(
              care
                  ? 'Care'
                  : s.staffRole == 'owner'
                  ? 'Clinic'
                  : s.staffRole == 'care'
                  ? 'CSKH'
                  : s.staffRole == 'doctor'
                  ? 'Bác sĩ'
                  : 'Kế toán',
            ),
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
      bottomNavigationBar: PemaModernBottomNav(
        selectedIndex: index,
        onDestinationSelected: (i) => setState(() => index = i),
        destinations: List.generate(
          labels.length,
          (i) => NavigationDestination(icon: Icon(icons[i]), label: labels[i]),
        ),
      ),
    );
  }

  List<Widget> accountPicker() => [
    section('Tài khoản mẫu · 10 nhóm CSKH'),
    DropdownButtonFormField<String>(
      key: ValueKey('group-$caseGroup'),
      initialValue: caseGroup,
      isExpanded: true,
      items: [
        const DropdownMenuItem(value: 'all', child: Text('Tất cả hồ sơ')),
        ...catalog.profiles
            .where((p) => p['group'] != '')
            .map(
              (p) => DropdownMenuItem(
                value: p['group'] as String,
                child: Text(p['case'] as String),
              ),
            ),
      ],
      onChanged: (v) {
        setState(() => caseGroup = v!);
        if (v != 'all') {
          select(catalog.profiles.indexWhere((p) => p['group'] == v));
        }
      },
    ),
    const SizedBox(height: 12),
    DropdownButtonFormField<int>(
      key: ValueKey('patient-${s.selected}-$caseGroup'),
      isExpanded: true,
      initialValue: caseGroup == 'all' || profile['group'] == caseGroup
          ? s.selected
          : null,
      decoration: const InputDecoration(labelText: 'Người bệnh đang xem'),
      items: [
        for (int i = 0; i < catalog.profiles.length; i++)
          if (caseGroup == 'all' || catalog.profiles[i]['group'] == caseGroup)
            DropdownMenuItem(
              value: i,
              child: Text(
                '${catalog.profiles[i]['id']} · ${catalog.profiles[i]['name']}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
      ],
      onChanged: (i) => select(i!),
    ),
  ];
  List<Widget> patientNext() {
    final group = profile['group'] as String;
    final title = {
      'd1': 'Hôm nay bạn cảm thấy thế nào?',
      'd3': 'Cập nhật ảnh tiến triển',
      'd7': 'Cùng bác sĩ xem lại tiến triển',
      'due': 'Đến mốc tái khám',
      'overdue': 'Sắp xếp lần tái khám tiếp theo',
      'no_show': 'Chọn lại một lịch hẹn phù hợp',
      'abandoned': 'Tiếp tục kế hoạch chăm sóc',
      'dormant90': 'Pema sẵn sàng đồng hành',
      'dormant180': 'Kết nối lại với Pema',
      'birthday': 'Pema chúc bạn sinh nhật nhiều sức khỏe',
    }[group];
    if (title == null) return [];
    return [
      tile(
        title,
        'Xem lịch hoặc gửi nhu cầu để đội ngũ hỗ trợ',
        Icons.favorite_outline,
        () => open(group == 'due' ? 'Lịch của tôi' : 'Gửi cập nhật'),
      ),
    ];
  }

  List<Widget> staffBody() {
    if (index == 1)
      return [
        heading('Hồ sơ phụ trách', s.staffName),
        PatientSearch(
          onOpen: () => open(
            s.staffRole == 'care'
                ? 'Chăm sóc khách hàng'
                : s.staffRole == 'accountant'
                ? 'Hóa đơn'
                : 'Patient 360',
          ),
        ),
      ];
    if (s.staffRole == 'accountant')
      return [
        heading('Đối soát & thu ngân', 'Kế toán · không gian riêng'),
        if (finance != null)
          tile(
            'Tài chính & tiền thủ thuật',
            'Đối soát, phiếu thu, chính sách và chốt kỳ',
            Icons.account_balance_wallet_outlined,
            () => openFinance(),
          ),
        tile(
          'Thu ngân theo hồ sơ',
          name,
          Icons.receipt_long_outlined,
          () => open('Thu ngân'),
        ),
      ];
    if (s.staffRole == 'doctor')
      return [
        heading('Lịch & hồ sơ của tôi', s.staffName),
        tile(
          'Hồ sơ đang phụ trách',
          name,
          Icons.person_outline,
          () => open('Patient 360'),
        ),
        tile(
          'Lịch của tôi',
          patient.day.isEmpty ? 'Chưa có lịch' : patient.day,
          Icons.calendar_month_outlined,
          () => open('Chi tiết lịch'),
        ),
        if (finance != null)
          tile(
            'Doanh số của tôi',
            'Chỉ số cá nhân và tiền thủ thuật',
            Icons.account_balance_wallet_outlined,
            () => openFinance(),
          ),
        section('Cập nhật cần bác sĩ xem'),
        for (int i = 0; i < catalog.profiles.length; i++)
          if (s.owns(catalog.profiles[i]) &&
              ((catalog.profiles[i]['tasks'] as List).any(
                    (t) => t['type'] == 'd7',
                  ) ||
                  (states[catalog.profiles[i]['id']]?.updates.isNotEmpty ??
                      false) ||
                  (states[catalog.profiles[i]['id']]?.escalations.isNotEmpty ??
                      false)))
            tile(
              catalog.profiles[i]['name'],
              'Review chăm sóc · hồ sơ phụ trách',
              Icons.inbox_outlined,
              () {
                select(i);
                open('Phản hồi');
              },
            ),
      ];
    return [CareQueue(onOpen: () => open('Chăm sóc khách hàng'))];
  }

  List<Widget> body() {
    if (care) {
      if (index == 1)
        return [
          heading('Hành trình của bạn', 'Mỗi bước chăm sóc đều được ghi nhận'),
          hero(
            'Phục hồi & chăm sóc da',
            '${patient.sessions}/${profile['total']} buổi đã hoàn tất',
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
          ...patient.updates.map(
            (x) => tile('Bạn', x, Icons.chat_bubble_outline, null),
          ),
          if (patient.response.isNotEmpty)
            tile(
              'Đội ngũ Pema',
              patient.response,
              Icons.verified_outlined,
              null,
            ),
          primary('Gửi cập nhật', () => open('Gửi cập nhật')),
        ];
      if (index == 3)
        return [
          heading(name, '${profile['id']} · Hồ sơ minh họa'),
          ...accountPicker(),
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
        heading(
          'Chào ${name.split(' ').last},',
          'Hôm nay, dành chút thời gian cho làn da',
        ),
        ...patientNext(),
        hero(
          'Chăm sóc nhẹ nhàng.\nĐồng hành mỗi ngày.',
          'Liệu trình phục hồi · Buổi ${patient.sessions}/${profile['total']}',
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
          patient.day.isEmpty
              ? 'Chưa có lịch hẹn'
              : '${patient.appointment} · ${patient.day}',
          'BS. Tâm · Khám da liễu',
          Icons.calendar_today_outlined,
          () => open('Lịch của tôi'),
        ),
        section('Việc cần làm'),
        tile(
          patient.acknowledged
              ? 'Đã đọc hướng dẫn'
              : 'Đọc hướng dẫn sau điều trị',
          'Bác sĩ đã gửi hướng dẫn cho bạn',
          patient.acknowledged
              ? Icons.check_circle_outline
              : Icons.favorite_outline,
          () => open('Chăm sóc tại nhà'),
        ),
      ];
    }
    if (s.staffRole != 'owner') return staffBody();
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
        for (final time in ['09:00', patient.appointment, '14:00'])
          tile(
            time,
            time == patient.appointment
                ? '${name} · Tái khám'
                : 'Khung giờ trống',
            Icons.schedule,
            () => open('Chi tiết lịch'),
          ),
        primary('Đặt / dời lịch', () => open('Đặt lịch')),
      ];
    if (index == 2)
      return [
        heading(
          'Hồ sơ người bệnh',
          '${catalog.profiles.length} hồ sơ tổng hợp · Patient 360',
        ),
        PatientSearch(onOpen: () => open('Patient 360')),
      ];
    if (index == 3)
      return [
        heading('Theo dõi', 'Ưu tiên phản hồi và bàn giao'),
        notice(
          '${patient.updates.length} cập nhật · ${patient.response.isEmpty ? '1 cần phản hồi' : 'Đã phản hồi'}',
        ),
        ...patient.updates.map(
          (x) =>
              tile(name, x, Icons.chat_bubble_outline, () => open('Phản hồi')),
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
        if (finance != null)
          tile(
            'Tài chính & tiền thủ thuật',
            'Chủ phòng khám · Kế toán · Bác sĩ',
            Icons.account_balance_wallet_outlined,
            () => openFinance(),
          ),
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
        '${patient.updates.length} phản hồi cần theo dõi',
        Icons.wb_sunny_outlined,
      ),
      const SizedBox(height: 16),
      Row(
        children: [
          metric('12', 'Lịch hôm nay'),
          const SizedBox(width: 12),
          metric(patient.checkedIn ? '04' : '03', 'Đang chờ'),
        ],
      ),
      if (finance != null)
        tile(
          'Tài chính phòng khám',
          finance!.data == null
              ? 'Doanh số · thực thu · tiền thủ thuật'
              : 'Tháng ${finance!.month} · ${cash(finance!.data!["summary"]["revenue"])}',
          Icons.account_balance_wallet_outlined,
          () => openFinance(),
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
        name,
        '${patient.appointment} · ${patient.checkedIn ? 'Đã check-in' : 'Chờ tiếp nhận'} · Tái khám',
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

class PatientSearch extends ConsumerStatefulWidget {
  final VoidCallback onOpen;
  const PatientSearch({super.key, required this.onOpen});
  @override
  ConsumerState<PatientSearch> createState() => _PatientSearchState();
}

class _PatientSearchState extends ConsumerState<PatientSearch> {
  String query = '';
  @override
  Widget build(BuildContext context) {
    final profiles = ref.watch(catalogProvider).profiles;
    final session = ref.watch(sessionProvider);
    return Column(
      children: [
        TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search),
            hintText: 'Tìm tên hoặc mã hồ sơ',
          ),
          onChanged: (v) => setState(() => query = v.toLowerCase()),
        ),
        const SizedBox(height: 16),
        for (int i = 0; i < profiles.length; i++)
          if (session.owns(profiles[i]) &&
              ((profiles[i]['name'] as String).toLowerCase().contains(query) ||
                  'p${(i + 1).toString().padLeft(3, '0')}'.contains(query)))
            tile(
              profiles[i]['name'] as String,
              'P${(i + 1).toString().padLeft(3, '0')} · Đang điều trị',
              Icons.person_outline,
              () {
                ref.read(sessionProvider.notifier).select(i);
                widget.onOpen();
              },
            ),
      ],
    );
  }
}

class Detail extends ConsumerStatefulWidget {
  final String route;
  const Detail({super.key, required this.route});
  @override
  ConsumerState<Detail> createState() => _DetailState();
}

class _DetailState extends ConsumerState<Detail> {
  final text = TextEditingController();
  bool consent = false, photo = false;
  String filter = '';
  late Session s;
  late Catalog catalog;
  late Map<String, dynamic> profile;
  late PatientState patient;
  late List<Order> orders;
  late int paid;
  FinanceState? finance;
  bool get care => s.careMode;
  String get id => profile['id'] as String;
  String get name => profile['name'] as String;
  int get totalSessions => profile['total'] as int;
  PatientsNotifier get patients => ref.read(patientsProvider.notifier);
  void patch(PatientState Function(PatientState) change) =>
      patients.update(id, change);

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  void open(String route) => Navigator.push(
    context,
    MaterialPageRoute(builder: (_) => Detail(route: route)),
  );
  void toast(String message) => ScaffoldMessenger.of(
    context,
  ).showSnackBar(SnackBar(content: Text(message)));
  @override
  Widget build(BuildContext context) {
    s = ref.watch(sessionProvider);
    catalog = ref.watch(catalogProvider);
    profile = ref.watch(selectedProfileProvider);
    patient = ref.watch(currentPatientProvider);
    orders = ref.watch(currentOrdersProvider);
    paid = ref.watch(currentPaidProvider);
    finance = ref.watch(financeEnabledProvider)
        ? ref.watch(financeProvider)
        : null;
    return Scaffold(
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
  }

  List<Widget> content() {
    if (!s.allows(widget.route))
      return [
        notice(
          'Tác vụ không thuộc không gian hiện tại. Quay lại để chọn đúng công việc.',
        ),
      ];
    switch (widget.route) {
      case 'Chăm sóc khách hàng':
        return [
          heading(name, '${id} · ${profile['case']}'),
          notice('Nội dung liên hệ nội bộ không hiển thị cho người bệnh.'),
          if (patient.careNote.isNotEmpty) notice(patient.careNote),
          TextField(
            controller: text,
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: 'Kết quả liên hệ / việc cần bàn giao',
            ),
          ),
          primary('Lưu kết quả liên hệ', () {
            if (text.text.trim().isEmpty) {
              toast('Nhập kết quả liên hệ');
              return;
            }
            patch(
              (p) => p.copyWith(
                careNote: text.text.trim(),
                careStatus: 'Đã liên hệ',
              ),
            );
            toast('Đã lưu ghi chú nội bộ');
          }),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              minimumSize: const Size.fromHeight(48),
              backgroundColor: Colors.white,
              side: const BorderSide(color: Color(0xFFCADBE8)),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
              ),
            ),
            onPressed: () => open('Đặt lịch'),
            icon: const Icon(Icons.calendar_month_outlined),
            label: const Text('Hỗ trợ đặt lại lịch'),
          ),
          TextButton.icon(
            icon: const Icon(Icons.forward_to_inbox_outlined),
            label: const Text('Chuyển bác sĩ xem'),
            onPressed: () {
              if (text.text.trim().isEmpty) {
                toast('Nhập nội dung cần bác sĩ xem');
                return;
              }
              patch(
                (p) => p.copyWith(
                  careNote: text.text.trim(),
                  careStatus: 'Chờ bác sĩ',
                  escalations: [...p.escalations, text.text.trim()],
                ),
              );
              toast('Đã chuyển vào hàng chờ bác sĩ');
            },
          ),
        ];
      case 'Patient 360':
        return [
          heading(name, '${id} · ${profile['doctor']}'),
          notice('Da nhạy cảm • Cần đọc tiền sử trước khi kê đơn'),
          Row(
            children: [
              metric('${patient.sessions}/${totalSessions}', 'Buổi điều trị'),
              const SizedBox(width: 12),
              metric(patient.appointment, 'Lịch tiếp theo'),
            ],
          ),
          if (!care &&
              s.billing &&
              finance?.data != null &&
              finance!.role != 'doctor')
            tile(
              'Ghi nhận tiền thủ thuật',
              'Đúng người thực hiện · gắn hóa đơn đã có',
              Icons.receipt_long_outlined,
              () => Navigator.push(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => ProcedureForm(
                    initialPatient: id,
                    patientIds: catalog.patientIds,
                  ),
                ),
              ),
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
            patient.checkedIn ? 'Đã check-in' : 'Check-in người bệnh',
            patient.checkedIn
                ? null
                : () => patch((p) => p.copyWith(checkedIn: true)),
          ),
        ];
      case 'Lên đơn nhanh':
        return [
          notice(
            '${name} · ${id}\n115 sản phẩm từ catalog web. Đơn nháp chưa gửi cho người bệnh.',
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
            'Xem đơn · ${patient.cart.length} sản phẩm · ${money(patient.cartTotal)}',
            patient.cart.isEmpty ? null : () => open('Kiểm tra đơn'),
          ),
          for (final p
              in catalog.products
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
                patients.addToCart(id, p);
                toast('Đã thêm ${p['code']}');
              },
            ),
        ];
      case 'Kiểm tra đơn':
        return [
          heading(
            'Kiểm tra trước khi duyệt',
            '${patient.cart.length} dòng · ${money(patient.cartTotal)}',
          ),
          for (final (i, line) in patient.cart.indexed)
            Card(
              key: ValueKey(line.code),
              elevation: 0,
              color: Colors.white,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      line.name,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    Row(
                      children: [
                        IconButton(
                          tooltip: 'Giảm số lượng',
                          onPressed: () => patients.updateLine(
                            id,
                            i,
                            (l) => l.copyWith(
                              quantity: l.quantity > 1 ? l.quantity - 1 : 1,
                            ),
                          ),
                          icon: const Icon(Icons.remove_circle_outline),
                        ),
                        Text('${line.quantity} ${line.unit}'),
                        IconButton(
                          tooltip: 'Tăng số lượng',
                          onPressed: () => patients.updateLine(
                            id,
                            i,
                            (l) => l.copyWith(quantity: l.quantity + 1),
                          ),
                          icon: const Icon(Icons.add_circle_outline),
                        ),
                        const Spacer(),
                        IconButton(
                          tooltip: 'Xóa dòng',
                          onPressed: () => patients.removeLine(id, i),
                          icon: const Icon(Icons.delete_outline),
                        ),
                      ],
                    ),
                    DropdownButtonFormField<String>(
                      initialValue: line.route,
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
                      onChanged: (v) => patients.updateLine(
                        id,
                        i,
                        (l) => l.copyWith(route: v),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      initialValue: line.usage,
                      decoration: const InputDecoration(
                        labelText: 'Cách dùng / hướng dẫn',
                      ),
                      onChanged: (v) => patients.updateLine(
                        id,
                        i,
                        (l) => l.copyWith(usage: v),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          notice(
            'Tài khoản bác sĩ mô phỏng. Chỉ duyệt khi đã phân loại và nhập hướng dẫn cho mọi dòng.',
          ),
          primary(
            'Lưu nháp',
            patient.cart.isEmpty
                ? null
                : () {
                    ref.read(ordersProvider.notifier).save(id, approve: false);
                    open('Đơn thuốc & tư vấn');
                  },
          ),
          primary(
            'Bác sĩ duyệt đơn',
            patient.cartReady
                ? () {
                    ref.read(ordersProvider.notifier).save(id, approve: true);
                    open('Đơn thuốc & tư vấn');
                  }
                : null,
          ),
        ];
      case 'Đơn thuốc & tư vấn':
        return [
          notice(
            care
                ? 'Chỉ hiển thị nội dung đã được bác sĩ duyệt.'
                : 'Nháp → bác sĩ duyệt → người bệnh xem. In không đồng nghĩa đã cấp thuốc.',
          ),
          if (orders.where((o) => !care || o.approved).isEmpty)
            tile(
              'Chưa có đơn${care ? ' đã duyệt' : ''}',
              'Đơn mới sẽ xuất hiện tại đây',
              Icons.receipt_long_outlined,
              null,
            ),
          for (final o in orders.where((o) => !care || o.approved)) ...[
            section('${o.id} · ${o.approved ? 'Đã duyệt' : 'Nháp'}'),
            for (final route in ['PRESCRIPTION', 'CONSULTATION']) ...[
              Text(
                route == 'PRESCRIPTION' ? 'Đơn thuốc' : 'Phiếu tư vấn',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              for (final line in o.items.where((l) => l.route == route))
                tile(
                  line.name,
                  '${line.quantity} ${line.unit} · ${line.usage}',
                  Icons.medication_outlined,
                  null,
                ),
            ],
            if (!care && !o.approved)
              primary('Sửa và duyệt bản nháp', () {
                ref.read(ordersProvider.notifier).edit(id, o);
                open('Kiểm tra đơn');
              }),
            if (!care)
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
                    Text(name),
                    const Divider(),
                    for (final o in orders.where((o) => o.approved))
                      for (final line in o.items.where(
                        (l) =>
                            l.route ==
                            (kind == 'ĐƠN THUỐC'
                                ? 'PRESCRIPTION'
                                : 'CONSULTATION'),
                      ))
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: Text(
                            '${line.name}\n${line.quantity} ${line.unit} · ${line.usage}',
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
          heading(name, 'Chọn ngày và giờ trước khi xác nhận'),
          const WeekStrip(),
          tile(
            patient.day,
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
                patch((p) => p.copyWith(day: '${d.day}/${d.month}/${d.year}'));
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
                    selected: patient.appointment == t,
                    onSelected: t == '09:00'
                        ? null
                        : (_) => patch((p) => p.copyWith(appointment: t)),
                  ),
                )
                .toList(),
          ),
          primary('Xác nhận lịch', () {
            patch((p) => p.copyWith(confirmed: true));
            toast('Đã lưu lịch ${patient.appointment} · ${patient.day}');
            Navigator.pop(context);
          }),
        ];
      case 'Chi tiết lịch':
      case 'Lịch của tôi':
        return [
          hero(
            patient.day.isEmpty
                ? 'Chưa có lịch hẹn'
                : '${patient.appointment} · ${patient.day}',
            'BS. Tâm · Khám da liễu',
            Icons.calendar_month_outlined,
          ),
          section(name),
          notice('Tái khám & đánh giá · 30 phút'),
          primary(
            patient.confirmed ? 'Đã xác nhận' : 'Xác nhận tham dự',
            patient.confirmed || patient.day.isEmpty
                ? null
                : () => patch((p) => p.copyWith(confirmed: true)),
          ),
          if (!care) primary('Dời lịch', () => open('Đặt lịch')),
          if (!care) primary('Mở Patient 360', () => open('Patient 360')),
        ];
      case 'Tư vấn':
        return [
          notice('Ghi chú chuyên môn là bản nháp, cần bác sĩ xem lại.'),
          TextField(
            controller: text,
            maxLines: 6,
            decoration: InputDecoration(
              labelText: 'Ghi chú tư vấn',
              hintText: patient.note,
            ),
          ),
          primary('Lưu ghi chú nháp', () {
            patch((p) => p.copyWith(note: text.text));
            toast('Đã lưu ghi chú');
          }),
          primary('Xem tóm tắt AI', () => open('Ask Pema')),
        ];
      case 'Kế hoạch điều trị':
        return [
          hero(
            'Phục hồi & chăm sóc da',
            '${patient.sessions}/${totalSessions} buổi · BS. Tâm',
            Icons.route_outlined,
          ),
          section('Các mốc chăm sóc'),
          for (int i = 1; i <= 5; i++)
            tile(
              'Buổi $i',
              i <= patient.sessions
                  ? 'Đã hoàn tất'
                  : 'Chờ đánh giá / thực hiện',
              i <= patient.sessions
                  ? Icons.check_circle_outline
                  : Icons.circle_outlined,
              null,
            ),
          primary('Xem chăm sóc tại nhà', () => open('Chăm sóc tại nhà')),
        ];
      case 'Buổi điều trị':
        return [
          notice(
            'Buổi ${patient.sessions + 1}/${totalSessions} · ${profile['doctor']}',
          ),
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
            consent &&
                    text.text.trim().isNotEmpty &&
                    patient.sessions < totalSessions
                ? () {
                    patch((p) => p.copyWith(sessions: p.sessions + 1));
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
            patient.acknowledged
                ? 'Đã xác nhận đã đọc'
                : 'Tôi đã đọc hướng dẫn',
            patient.acknowledged
                ? null
                : () => patch((p) => p.copyWith(acknowledged: true)),
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
                    patch(
                      (p) => p.copyWith(updates: [...p.updates, text.text]),
                    );
                    toast('Đã gửi • Chờ đội ngũ xem');
                    Navigator.pop(context);
                  }
                : null,
          ),
        ];
      case 'Phản hồi':
        return [
          ...patient.escalations.map((x) => notice('CSKH bàn giao nội bộ: $x')),
          heading(name, 'Cập nhật từ Patient Mobile'),
          ...patient.updates.map((x) => notice(x)),
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
                    patch((p) => p.copyWith(response: text.text));
                    toast('Đã gửi phản hồi sang Pema Care');
                    Navigator.pop(context);
                  }
                : null,
          ),
        ];
      case 'Hóa đơn':
      case 'Thu ngân':
        final amount = orders.fold<int>(0, (n, o) => n + o.total);
        return [
          heading('Khoản cần thanh toán', name),
          hero(
            money(amount - paid),
            'Đã thu ${money(paid)}',
            Icons.payments_outlined,
          ),
          ...orders.map(
            (o) =>
                tile(o.id, money(o.total), Icons.receipt_long_outlined, null),
          ),
          if (!care && s.billing)
            primary(
              'Thu đủ phần còn lại',
              amount > paid
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
                                money(amount - paid),
                              ),
                              notice('Giao dịch mẫu · Không kết nối ngân hàng'),
                              primary('Xác nhận tiền mặt', () {
                                ref
                                    .read(receiptsProvider.notifier)
                                    .settle(id, amount);
                                Navigator.pop(ctx);
                              }),
                            ],
                          ),
                        ),
                      ),
                    )
                  : null,
            ),
          if (!care && s.clinical)
            primary('Lên đơn mới', () => open('Lên đơn nhanh')),
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
          section('Tóm tắt ${name}'),
          notice(
            'Đã hoàn tất ${patient.sessions}/${totalSessions} buổi. Có ${patient.updates.length} phản hồi tại nhà.\nNguồn: hành trình và cập nhật trong phiên mẫu.',
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
