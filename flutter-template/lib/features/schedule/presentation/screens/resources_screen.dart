import 'package:flutter/material.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';

class ResourcesScreen extends StatelessWidget {
  const ResourcesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.resources,
      children: [
        heading('Nguồn lực phòng khám', 'Chạm lịch để điều phối theo ca'),
        for (final name in ['BS. Tâm', 'BS. Mai', 'BS. An', 'BS. Lan'])
          tile(
            name,
            '08:00–18:00 · Nghỉ 12:00–13:00',
            Icons.medical_services_outlined,
            () => open(AppRoutes.booking),
          ),
        notice(
          'Laser & thủ thuật · Bảo trì 14:00–15:00 ngày 23/09. Khóa phòng phức tạp duyệt ở web.',
        ),
      ],
    );
  }
}
