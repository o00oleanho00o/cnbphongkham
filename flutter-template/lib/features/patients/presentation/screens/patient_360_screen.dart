import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../catalog/presentation/providers/catalog_provider.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../domain/models/patient_state.dart';
import '../providers/patients_provider.dart';
import '../../../finance/presentation/providers/finance_provider.dart';
import '../../../finance/presentation/screens/procedure_form_screen.dart';

class Patient360Screen extends ConsumerWidget {
  const Patient360Screen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(sessionProvider);
    final care = s.careMode;
    final profile = ref.watch(selectedProfileProvider);
    final name = profile['name'] as String;
    final id = profile['id'] as String;
    final totalSessions = profile['total'] as int;
    final patient = ref.watch(currentPatientProvider);
    final canRecordProcedure =
        ref.watch(financeEnabledProvider) &&
        ref.watch(
          financeProvider.select((f) => f.data != null && f.role != 'doctor'),
        );
    final catalog = ref.watch(catalogProvider);
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.patient360,
      children: [
        heading(name, '${id} · ${profile['doctor']}'),
        notice('Da nhạy cảm • Cần đọc tiền sử trước khi kê đơn'),
        Row(
          children: [
            metric('${patient.sessions}/${totalSessions}', 'Buổi điều trị'),
            const SizedBox(width: 12),
            metric(patient.appointment, 'Lịch tiếp theo'),
          ],
        ),
        if (!care && s.billing && canRecordProcedure)
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
          (x) => tile(x, 'Xem và cập nhật', Icons.chevron_right, () => open(x)),
        ),
        primary(
          patient.checkedIn ? 'Đã check-in' : 'Check-in người bệnh',
          patient.checkedIn
              ? null
              : () => patch((p) => p.copyWith(checkedIn: true)),
        ),
      ],
    );
  }
}
