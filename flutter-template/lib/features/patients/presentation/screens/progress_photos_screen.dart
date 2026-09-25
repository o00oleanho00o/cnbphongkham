import 'package:flutter/material.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';

class ProgressPhotosScreen extends StatelessWidget {
  const ProgressPhotosScreen({super.key});

  @override
  Widget build(BuildContext context) {
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.progressPhotos,
      children: [
        heading(
          'Theo dõi bằng hình ảnh',
          'Ảnh minh họa • không đánh giá hiệu quả tự động',
        ),
        Row(
          children: [
            for (final label in ['Trước', 'Gần nhất'])
              Expanded(
                child: Container(
                  margin: const EdgeInsets.all(4),
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
          ],
        ),
        notice('Chính diện · Vùng mặt · Cần cùng điều kiện ánh sáng'),
        primary('Gửi ảnh cập nhật', () => open(AppRoutes.sendUpdate)),
      ],
    );
  }
}
