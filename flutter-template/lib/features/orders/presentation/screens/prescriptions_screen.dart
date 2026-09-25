import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../providers/orders_provider.dart';

class PrescriptionsScreen extends ConsumerWidget {
  const PrescriptionsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final care = ref.watch(sessionProvider.select((s) => s.careMode));
    final profile = ref.watch(selectedProfileProvider);
    final id = profile['id'] as String;
    final orders = ref.watch(currentOrdersProvider);
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.prescriptions,
      children: [
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
              open(AppRoutes.orderReview);
            }),
          if (!care)
            primary('Xem bố cục hai phiếu A5', () => open(AppRoutes.a5Print)),
        ],
      ],
    );
  }
}
