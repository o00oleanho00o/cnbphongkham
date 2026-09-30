import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../providers/patients_provider.dart';

class TreatmentPlanScreen extends ConsumerWidget {
  const TreatmentPlanScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(selectedProfileProvider);
    final totalSessions = profile.totalSessions;
    final patient = ref.watch(currentPatientProvider);
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.treatmentPlan,
      children: [
        hero(
          'Phục hồi & chăm sóc da',
          '${patient.sessions}/${totalSessions} buổi · BS. Tâm',
          Icons.route_outlined,
        ),
        section('Các mốc chăm sóc'),
        for (int i = 1; i <= 5; i++)
          tile(
            'Buổi $i',
            i <= patient.sessions ? 'Đã hoàn tất' : 'Chờ đánh giá / thực hiện',
            i <= patient.sessions
                ? Icons.check_circle_outline
                : Icons.circle_outlined,
            null,
          ),
        primary('Xem chăm sóc tại nhà', () => open(AppRoutes.homeCare)),
      ],
    );
  }
}
