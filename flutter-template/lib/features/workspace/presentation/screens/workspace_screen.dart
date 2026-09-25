import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/money_format.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../../core/widgets/pema_bottom_nav.dart';
import '../../../catalog/domain/models/catalog.dart';
import '../../../catalog/presentation/providers/catalog_provider.dart';
import '../../../session/domain/models/session.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/domain/models/patient_state.dart';
import '../../../patients/presentation/providers/patients_provider.dart';
import '../../../patients/presentation/widgets/patient_search.dart';
import '../../../finance/presentation/providers/finance_provider.dart';
import '../../../schedule/presentation/widgets/week_strip.dart';
import '../../../customer_care/presentation/widgets/care_queue.dart';

class WorkspaceScreen extends ConsumerStatefulWidget {
  const WorkspaceScreen({super.key});
  @override
  ConsumerState<WorkspaceScreen> createState() => _WorkspaceScreenState();
}

class _WorkspaceScreenState extends ConsumerState<WorkspaceScreen> {
  int index = 0;
  String caseGroup = 'all';
  late Session s;
  late Catalog catalog;
  late Map<String, dynamic> profile;
  late PatientState patient;
  late Map<String, PatientState> states;
  bool financeOn = false;
  bool get care => s.careMode;
  String get name => profile['name'] as String;

  @override
  void initState() {
    super.initState();
    if (ref.read(financeEnabledProvider)) {
      ref.read(financeProvider.notifier).start();
    }
  }

  void openFinance([int tab = 0]) => context.openFinance(tab);

  void select(int i) => ref.read(sessionProvider.notifier).select(i);

  void open(String route) {
    if (!ref.read(sessionProvider).allows(route)) return;
    context.openRoute(route);
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
              Icon(icon, color: AppColors.blue),
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
    financeOn = ref.watch(financeEnabledProvider);
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
          if (!care && s.staffRole == 'owner' && financeOn)
            IconButton(
              onPressed: () => openFinance(3),
              tooltip: 'Thông báo thanh toán',
              icon: const _UnreadBadge(),
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
        if (financeOn)
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
          () => open(AppRoutes.cashier),
        ),
      ];
    if (s.staffRole == 'doctor')
      return [
        heading('Lịch & hồ sơ của tôi', s.staffName),
        tile(
          'Hồ sơ đang phụ trách',
          name,
          Icons.person_outline,
          () => open(AppRoutes.patient360),
        ),
        tile(
          'Lịch của tôi',
          patient.day.isEmpty ? 'Chưa có lịch' : patient.day,
          Icons.calendar_month_outlined,
          () => open(AppRoutes.appointmentDetail),
        ),
        if (financeOn)
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
                open(AppRoutes.followUpReply);
              },
            ),
      ];
    return [CareQueue(onOpen: () => open(AppRoutes.customerCare))];
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
          primary('Gửi cập nhật', () => open(AppRoutes.sendUpdate)),
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
          () => open(AppRoutes.myAppointments),
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
          () => open(AppRoutes.homeCare),
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
          () => open(AppRoutes.resources),
        ),
        for (final time in ['09:00', patient.appointment, '14:00'])
          tile(
            time,
            time == patient.appointment
                ? '${name} · Tái khám'
                : 'Khung giờ trống',
            Icons.schedule,
            () => open(AppRoutes.appointmentDetail),
          ),
        primary('Đặt / dời lịch', () => open(AppRoutes.booking)),
      ];
    if (index == 2)
      return [
        heading(
          'Hồ sơ người bệnh',
          '${catalog.profiles.length} hồ sơ tổng hợp · Patient 360',
        ),
        PatientSearch(onOpen: () => open(AppRoutes.patient360)),
      ];
    if (index == 3)
      return [
        heading('Theo dõi', 'Ưu tiên phản hồi và bàn giao'),
        notice(
          '${patient.updates.length} cập nhật · ${patient.response.isEmpty ? '1 cần phản hồi' : 'Đã phản hồi'}',
        ),
        ...patient.updates.map(
          (x) => tile(
            name,
            x,
            Icons.chat_bubble_outline,
            () => open(AppRoutes.followUpReply),
          ),
        ),
        tile(
          'Cần gọi lại',
          'Hồ sơ mẫu · triệu chứng tăng',
          Icons.priority_high,
          () => open(AppRoutes.followUpReply),
        ),
      ];
    if (index == 4)
      return [
        heading('Không gian làm việc', 'Nghiệp vụ theo đúng hành trình Pema'),
        if (financeOn)
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
      if (financeOn) _FinanceSummaryTile(onTap: openFinance),
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
        () => open(AppRoutes.patient360),
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

/// Only this badge rebuilds when the unread count changes.
class _UnreadBadge extends ConsumerWidget {
  const _UnreadBadge();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final unread = ref.watch(financeProvider.select((f) => f.unread));
    return Badge(
      isLabelVisible: unread > 0,
      label: Text('$unread'),
      child: const Icon(Icons.notifications_outlined),
    );
  }
}

/// Only this tile rebuilds when the monthly revenue changes.
class _FinanceSummaryTile extends ConsumerWidget {
  const _FinanceSummaryTile({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final subtitle = ref.watch(
      financeProvider.select(
        (f) => f.data == null
            ? 'Doanh số · thực thu · tiền thủ thuật'
            : 'Tháng ${f.month} · ${money(f.data!["summary"]["revenue"])}',
      ),
    );
    return tile(
      'Tài chính phòng khám',
      subtitle,
      Icons.account_balance_wallet_outlined,
      onTap,
    );
  }
}
