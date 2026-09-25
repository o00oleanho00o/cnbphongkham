import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/money_format.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/presentation/providers/patients_provider.dart';
import '../providers/orders_provider.dart';

class OrderReviewScreen extends ConsumerWidget {
  const OrderReviewScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(selectedProfileProvider);
    final id = profile['id'] as String;
    final patient = ref.watch(currentPatientProvider);
    final patients = ref.read(patientsProvider.notifier);
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.orderReview,
      children: [
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
                    onChanged: (v) =>
                        patients.updateLine(id, i, (l) => l.copyWith(route: v)),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    initialValue: line.usage,
                    decoration: const InputDecoration(
                      labelText: 'Cách dùng / hướng dẫn',
                    ),
                    onChanged: (v) =>
                        patients.updateLine(id, i, (l) => l.copyWith(usage: v)),
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
                  open(AppRoutes.prescriptions);
                },
        ),
        primary(
          'Bác sĩ duyệt đơn',
          patient.cartReady
              ? () {
                  ref.read(ordersProvider.notifier).save(id, approve: true);
                  open(AppRoutes.prescriptions);
                }
              : null,
        ),
      ],
    );
  }
}
