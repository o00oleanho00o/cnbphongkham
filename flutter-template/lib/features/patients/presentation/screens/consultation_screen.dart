import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/context_extensions.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../domain/models/patient_state.dart';
import '../providers/patients_provider.dart';

class ConsultationScreen extends ConsumerStatefulWidget {
  const ConsultationScreen({super.key});

  @override
  ConsumerState<ConsultationScreen> createState() => _ConsultationScreenState();
}

class _ConsultationScreenState extends ConsumerState<ConsultationScreen> {
  final text = TextEditingController();

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(selectedProfileProvider);
    final id = profile['id'] as String;
    final patient = ref.watch(currentPatientProvider);
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void open(String route) => context.openRoute(route);
    void toast(String message) => context.toast(message);
    return DetailScaffold(
      title: AppRoutes.consultation,
      children: [
        notice('Ghi chú chuyên môn là bản nháp, cần bác sĩ xem lại.'),
        TextField(
          controller: text,
          maxLines: 6,
          decoration: InputDecoration(
            labelText: 'Ghi chú tư vấn',
            hintText: patient.note,
          ),
        ),
        primary('Lưu ghi chú nháp', () {
          patch((p) => p.copyWith(note: text.text));
          toast('Đã lưu ghi chú');
        }),
        primary('Xem tóm tắt AI', () => open(AppRoutes.askPema)),
      ],
    );
  }
}
