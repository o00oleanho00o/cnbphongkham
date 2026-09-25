import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/camera/camera_service.dart';
import '../../../../core/camera/captured_photo.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/context_extensions.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/local_photo.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/presentation/providers/patients_provider.dart';

class SendUpdateScreen extends ConsumerStatefulWidget {
  const SendUpdateScreen({super.key});

  @override
  ConsumerState<SendUpdateScreen> createState() => _SendUpdateScreenState();
}

class _SendUpdateScreenState extends ConsumerState<SendUpdateScreen> {
  final text = TextEditingController();
  bool consent = false, capturing = false, sent = false;
  CapturedPhoto? photo;

  // Read once: `ref` must not be used from dispose().
  late final CameraService camera;

  @override
  void initState() {
    super.initState();
    camera = ref.read(cameraServiceProvider);
  }

  @override
  void dispose() {
    // A photo taken but never sent should not linger in the cache.
    if (!sent && photo != null) camera.discard(photo!);
    text.dispose();
    super.dispose();
  }

  Future<void> capture() async {
    setState(() => capturing = true);
    try {
      final next = await camera.capture();
      if (!mounted) return;
      if (next != null) {
        if (photo != null) await camera.discard(photo!);
        setState(() => photo = next);
      }
    } on CameraFailure catch (e) {
      if (mounted) context.toast(e.message);
    } finally {
      if (mounted) setState(() => capturing = false);
    }
  }

  void removePhoto() {
    camera.discard(photo!);
    setState(() {
      photo = null;
      consent = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final id = ref.watch(selectedPatientIdProvider);
    final photo = this.photo;
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
        const SizedBox(height: 12),
        if (photo != null) ...[
          LocalPhoto(path: photo.path, height: 260, label: 'Ảnh vừa chụp'),
          Row(
            children: [
              TextButton.icon(
                onPressed: capturing ? null : capture,
                icon: const Icon(Icons.refresh),
                label: const Text('Chụp lại'),
              ),
              TextButton.icon(
                onPressed: capturing ? null : removePhoto,
                icon: const Icon(Icons.delete_outline),
                label: const Text('Bỏ ảnh'),
              ),
            ],
          ),
          notice('Chụp chính diện, đủ sáng. Ảnh đã được bỏ thông tin vị trí.'),
          CheckboxListTile(
            value: consent,
            onChanged: (v) => setState(() => consent = v!),
            title: const Text('Tôi đồng ý chia sẻ ảnh để chăm sóc'),
          ),
        ] else
          OutlinedButton.icon(
            onPressed: capturing ? null : capture,
            icon: capturing
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.photo_camera_outlined),
            label: const Text('Chụp ảnh tiến triển'),
          ),
        primary(
          'Gửi cập nhật',
          text.text.trim().isNotEmpty && (photo == null || consent)
              ? () {
                  ref
                      .read(patientsProvider.notifier)
                      .update(
                        id,
                        (p) => p.copyWith(
                          updates: [...p.updates, text.text],
                          photos: [...p.photos, ?photo?.path],
                        ),
                      );
                  sent = true;
                  context.toast('Đã gửi • Chờ đội ngũ xem');
                  Navigator.pop(context);
                }
              : null,
        ),
      ],
    );
  }
}
