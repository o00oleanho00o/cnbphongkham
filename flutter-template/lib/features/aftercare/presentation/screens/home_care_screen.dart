import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/domain/models/patient_state.dart';
import '../../../patients/presentation/providers/patients_provider.dart';

class HomeCareScreen extends ConsumerWidget {
  const HomeCareScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(selectedProfileProvider);
    final id = profile.id;
    final patient = ref.watch(currentPatientProvider);
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.homeCare,
      children: [
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
          patient.acknowledged ? 'Đã xác nhận đã đọc' : 'Tôi đã đọc hướng dẫn',
          patient.acknowledged
              ? null
              : () => patch((p) => p.copyWith(acknowledged: true)),
        ),
        primary('Gửi cập nhật cho Pema', () => open(AppRoutes.sendUpdate)),
      ],
    );
  }
}
