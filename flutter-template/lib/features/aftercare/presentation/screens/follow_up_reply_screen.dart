import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/context_extensions.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/local_photo.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/domain/models/patient_state.dart';
import '../../../patients/presentation/providers/patients_provider.dart';

class FollowUpReplyScreen extends ConsumerStatefulWidget {
  const FollowUpReplyScreen({super.key});

  @override
  ConsumerState<FollowUpReplyScreen> createState() =>
      _FollowUpReplyScreenState();
}

class _FollowUpReplyScreenState extends ConsumerState<FollowUpReplyScreen> {
  final text = TextEditingController();

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(selectedProfileProvider);
    final name = profile.name;
    final id = profile.id;
    final patient = ref.watch(currentPatientProvider);
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void toast(String message) => context.toast(message);
    return DetailScaffold(
      title: AppRoutes.followUpReply,
      children: [
        ...patient.escalations.map((x) => notice('CSKH bàn giao nội bộ: $x')),
        heading(name, 'Cập nhật từ Patient Mobile'),
        ...patient.updates.map((x) => notice(x)),
        if (patient.photos.isNotEmpty) ...[
          SizedBox(
            height: 160,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: patient.photos.length,
              separatorBuilder: (_, _) => const SizedBox(width: 8),
              itemBuilder: (_, i) => SizedBox(
                width: 120,
                child: LocalPhoto(
                  path: patient.photos[i],
                  height: 160,
                  label: 'Ảnh ${i + 1}',
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
        ],
        TextField(
          controller: text,
          maxLines: 5,
          decoration: const InputDecoration(labelText: 'Phản hồi đã kiểm tra'),
          onChanged: (_) => setState(() {}),
        ),
        primary(
          'Duyệt và phản hồi',
          text.text.trim().isNotEmpty
              ? () {
                  patch((p) => p.copyWith(response: text.text));
                  toast('Đã gửi phản hồi sang Pema Care');
                  Navigator.pop(context);
                }
              : null,
        ),
      ],
    );
  }
}
