import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/context_extensions.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/domain/models/patient_state.dart';
import '../../../patients/presentation/providers/patients_provider.dart';

class SendUpdateScreen extends ConsumerStatefulWidget {
  const SendUpdateScreen({super.key});

  @override
  ConsumerState<SendUpdateScreen> createState() => _SendUpdateScreenState();
}

class _SendUpdateScreenState extends ConsumerState<SendUpdateScreen> {
  final text = TextEditingController();
  bool consent = false, photo = false;

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(selectedProfileProvider);
    final id = profile.id;
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void toast(String message) => context.toast(message);
    return DetailScaffold(
      title: AppRoutes.sendUpdate,
      children: [
        notice('Cập nhật sẽ vào hàng chờ để đội ngũ Pema xem.'),
        TextField(
          controller: text,
          maxLines: 5,
          decoration: const InputDecoration(
            labelText: 'Hôm nay da bạn thế nào?',
          ),
          onChanged: (_) => setState(() {}),
        ),
        primary(
          photo ? 'Đã chọn ảnh mẫu' : 'Đính kèm ảnh minh họa',
          () => setState(() => photo = !photo),
        ),
        if (photo) notice('Ảnh mẫu dùng duyệt UI • camera native chưa kết nối'),
        if (photo)
          CheckboxListTile(
            value: consent,
            onChanged: (v) => setState(() => consent = v!),
            title: const Text('Tôi đồng ý chia sẻ ảnh để chăm sóc'),
          ),
        primary(
          'Gửi cập nhật',
          text.text.trim().isNotEmpty && (!photo || consent)
              ? () {
                  patch((p) => p.copyWith(updates: [...p.updates, text.text]));
                  toast('Đã gửi • Chờ đội ngũ xem');
                  Navigator.pop(context);
                }
              : null,
        ),
      ],
    );
  }
}
