import 'package:flutter/material.dart';

import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';

class GuideScreen extends StatelessWidget {
  const GuideScreen({super.key, this.route = AppRoutes.guide});
  final String route;

  @override
  Widget build(BuildContext context) {
    return DetailScaffold(
      title: route,
      children: [
        heading('Một hành trình, nhiều điểm nối', 'Hướng dẫn sử dụng Pema'),
        ...[
          'Tiếp nhận → lịch → Patient 360',
          'Dịch vụ → kế hoạch → buổi điều trị',
          'Đơn nháp → bác sĩ duyệt → người bệnh xem',
          'Cập nhật tại nhà → theo dõi → phản hồi',
          'Hóa đơn → thu tiền → đối soát',
        ].map(
          (x) => tile(
            x,
            'Mỗi bàn giao cần người phụ trách và bước tiếp theo.',
            Icons.route_outlined,
            null,
          ),
        ),
        notice(
          'Duyệt Clinic/Care qua nút góc trên. Thao tác mẫu lưu trong bộ nhớ, tải lại sẽ bắt đầu phiên mới.',
        ),
      ],
    );
  }
}
