import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/money_format.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../orders/presentation/providers/orders_provider.dart';
import '../providers/receipts_provider.dart';

class CashierScreen extends ConsumerWidget {
  const CashierScreen({super.key, this.route = AppRoutes.cashier});
  final String route;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(sessionProvider);
    final care = s.careMode;
    final profile = ref.watch(selectedProfileProvider);
    final name = profile['name'] as String;
    final id = profile['id'] as String;
    final orders = ref.watch(currentOrdersProvider);
    final paid = ref.watch(currentPaidProvider);
    void open(String route) => context.openRoute(route);
    final amount = orders.fold<int>(0, (n, o) => n + o.total);
    return DetailScaffold(
      title: route,
      children: [
        heading('Khoản cần thanh toán', name),
        hero(
          money(amount - paid),
          'Đã thu ${money(paid)}',
          Icons.payments_outlined,
        ),
        ...orders.map(
          (o) => tile(o.id, money(o.total), Icons.receipt_long_outlined, null),
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
                            heading('Xác nhận thu tiền', money(amount - paid)),
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
          primary('Lên đơn mới', () => open(AppRoutes.quickOrder)),
      ],
    );
  }
}
