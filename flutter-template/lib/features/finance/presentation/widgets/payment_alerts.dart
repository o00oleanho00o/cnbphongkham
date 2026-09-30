import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../providers/finance_provider.dart';

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
              onPressed: () => appNavigatorKey.currentState!.pushNamed(
                AppRoutes.finance,
                arguments: 3,
              ),
            ),
          ),
        );
      });
    }
    return child;
  }
}
