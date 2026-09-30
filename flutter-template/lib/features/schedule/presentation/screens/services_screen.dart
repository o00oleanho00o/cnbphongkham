import 'package:flutter/material.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';

class ServicesScreen extends StatelessWidget {
  const ServicesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.services,
      children: [
        heading('Danh mục dịch vụ', 'Giá và thời lượng tham khảo như web'),
        for (final item in [
          'Tái khám & đánh giá|300.000 ₫ · 30 phút',
          'Tư vấn da liễu|500.000 ₫ · 45 phút',
          'Laser theo chỉ định|2.500.000 ₫ · 45 + 15 phút',
          'Chăm sóc theo chỉ định|1.200.000 ₫ · 45 + 15 phút',
        ])
          tile(
            item.split('|')[0],
            item.split('|')[1],
            Icons.spa_outlined,
            () => open(AppRoutes.booking),
          ),
      ],
    );
  }
}
