import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/local_photo.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../providers/patients_provider.dart';

class ProgressPhotosScreen extends ConsumerWidget {
  const ProgressPhotosScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final photos = ref.watch(currentPatientProvider.select((p) => p.photos));
    void open(String route) => context.openRoute(route);
    Widget slot(String label, String? path) => Expanded(
      child: Padding(
        padding: const EdgeInsets.all(4),
        child: path != null
            ? LocalPhoto(path: path, label: label)
            : Container(
                height: 220,
                decoration: BoxDecoration(
                  color: const Color(0xFFE8F4FB),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(
                      Icons.face_outlined,
                      size: 76,
                      color: Color(0xFF80B3D0),
                    ),
                    Text(label),
                    const Text('Minh họa', style: TextStyle(fontSize: 11)),
                  ],
                ),
              ),
      ),
    );
    return DetailScaffold(
      title: AppRoutes.progressPhotos,
      children: [
        heading(
          'Theo dõi bằng hình ảnh',
          photos.isEmpty
              ? 'Ảnh minh họa • không đánh giá hiệu quả tự động'
              : '${photos.length} ảnh đã gửi • không đánh giá hiệu quả tự động',
        ),
        Row(
          children: [
            slot('Trước', photos.length > 1 ? photos.first : null),
            slot('Gần nhất', photos.isEmpty ? null : photos.last),
          ],
        ),
        notice('Chính diện · Vùng mặt · Cần cùng điều kiện ánh sáng'),
        primary('Gửi ảnh cập nhật', () => open(AppRoutes.sendUpdate)),
      ],
    );
  }
}
