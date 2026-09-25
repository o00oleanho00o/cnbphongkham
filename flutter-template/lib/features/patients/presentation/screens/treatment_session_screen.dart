import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/context_extensions.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../domain/models/patient_state.dart';
import '../providers/patients_provider.dart';

class TreatmentSessionScreen extends ConsumerStatefulWidget {
  const TreatmentSessionScreen({super.key});

  @override
  ConsumerState<TreatmentSessionScreen> createState() =>
      _TreatmentSessionScreenState();
}

class _TreatmentSessionScreenState
    extends ConsumerState<TreatmentSessionScreen> {
  final text = TextEditingController();
  bool consent = false;

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(selectedProfileProvider);
    final id = profile['id'] as String;
    final totalSessions = profile['total'] as int;
    final patient = ref.watch(currentPatientProvider);
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void toast(String message) => context.toast(message);
    return DetailScaffold(
      title: AppRoutes.treatmentSession,
      children: [
        notice(
          'Buổi ${patient.sessions + 1}/${totalSessions} · ${profile['doctor']}',
        ),
        TextField(
          controller: text,
          maxLines: 4,
          decoration: const InputDecoration(
            labelText: 'Ghi nhận buổi điều trị *',
          ),
          onChanged: (_) => setState(() {}),
        ),
        CheckboxListTile(
          value: consent,
          onChanged: (v) => setState(() => consent = v!),
          title: const Text('Đã kiểm tra và bàn giao aftercare'),
        ),
        primary(
          'Hoàn tất buổi',
          consent &&
                  text.text.trim().isNotEmpty &&
                  patient.sessions < totalSessions
              ? () {
                  patch((p) => p.copyWith(sessions: p.sessions + 1));
                  toast('Đã lưu buổi và cập nhật hành trình');
                  Navigator.pop(context);
                }
              : null,
        ),
      ],
    );
  }
}
