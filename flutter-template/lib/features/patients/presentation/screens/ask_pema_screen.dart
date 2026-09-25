import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../providers/patients_provider.dart';

class AskPemaScreen extends ConsumerWidget {
  const AskPemaScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(selectedProfileProvider);
    final name = profile['name'] as String;
    final totalSessions = profile['total'] as int;
    final patient = ref.watch(currentPatientProvider);
    void open(String route) => context.openRoute(route);
    return DetailScaffold(
      title: AppRoutes.askPema,
      children: [
        hero(
          'Bối cảnh trước\nmỗi quyết định.',
          'AI mô phỏng • cần bác sĩ kiểm tra',
          Icons.auto_awesome_outlined,
        ),
        section('Tóm tắt ${name}'),
        notice(
          'Đã hoàn tất ${patient.sessions}/${totalSessions} buổi. Có ${patient.updates.length} phản hồi tại nhà.\nNguồn: hành trình và cập nhật trong phiên mẫu.',
        ),
        tile(
          'Việc còn mở',
          'Xem phản hồi trước khi khám lại.',
          Icons.inbox_outlined,
          () => open(AppRoutes.followUpReply),
        ),
        primary('Mở ghi chú để bác sĩ sửa', () => open(AppRoutes.consultation)),
      ],
    );
  }
}
