import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../providers/orders_provider.dart';

class A5PrintPreviewScreen extends ConsumerWidget {
  const A5PrintPreviewScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(selectedProfileProvider);
    final name = profile['name'] as String;
    final orders = ref.watch(currentOrdersProvider);
    return DetailScaffold(
      title: AppRoutes.a5Print,
      children: [
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
      ],
    );
  }
}
