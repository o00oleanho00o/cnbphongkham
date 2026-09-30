import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/context_extensions.dart';
import '../../../../core/utils/money_format.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../catalog/presentation/providers/catalog_provider.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/presentation/providers/patients_provider.dart';

class QuickOrderScreen extends ConsumerStatefulWidget {
  const QuickOrderScreen({super.key});

  @override
  ConsumerState<QuickOrderScreen> createState() => _QuickOrderScreenState();
}

class _QuickOrderScreenState extends ConsumerState<QuickOrderScreen> {
  String filter = '';

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(selectedProfileProvider);
    final name = profile.name;
    final id = profile.id;
    final patient = ref.watch(currentPatientProvider);
    final catalog = ref.watch(catalogProvider);
    final patients = ref.read(patientsProvider.notifier);
    void open(String route) => context.openRoute(route);
    void toast(String message) => context.toast(message);
    return DetailScaffold(
      title: AppRoutes.quickOrder,
      children: [
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
          patient.cart.isEmpty ? null : () => open(AppRoutes.orderReview),
        ),
        for (final p
            in catalog.products.where((p) => p.matches(filter)).take(20))
          tile(
            p.name,
            '${p.code} · ${p.unit} · ${money(p.price)}\n${p.needsClassification ? 'Cần phân loại' : p.sourceType}',
            Icons.add,
            () {
              patients.addToCart(id, p);
              toast('Đã thêm ${p.code}');
            },
          ),
      ],
    );
  }
}
