import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/domain/models/patient_state.dart';
import '../../../patients/presentation/providers/patients_provider.dart';

class AppointmentDetailScreen extends ConsumerWidget {
  const AppointmentDetailScreen({
    super.key,
    this.route = AppRoutes.appointmentDetail,
  });
  final String route;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final care = ref.watch(sessionProvider.select((s) => s.careMode));
    final profile = ref.watch(selectedProfileProvider);
    final name = profile.name;
    final id = profile.id;
    final patient = ref.watch(currentPatientProvider);
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: route,
      children: [
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
        if (!care) primary('Dời lịch', () => open(AppRoutes.booking)),
        if (!care) primary('Mở Patient 360', () => open(AppRoutes.patient360)),
      ],
    );
  }
}
