import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_routes.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';

class PrivacyScreen extends ConsumerStatefulWidget {
  const PrivacyScreen({super.key});

  @override
  ConsumerState<PrivacyScreen> createState() => _PrivacyScreenState();
}

class _PrivacyScreenState extends ConsumerState<PrivacyScreen> {
  bool consent = false;

  @override
  Widget build(BuildContext context) {
    return DetailScaffold(
      title: AppRoutes.privacy,
      children: [
        notice('Template không sử dụng dữ liệu bệnh nhân thật.'),
        CheckboxListTile(
          value: consent,
          onChanged: (v) => setState(() => consent = v!),
          title: const Text('Đồng ý dùng ảnh trong chăm sóc'),
        ),
        const Text('Cài đặt đang được minh họa trong phiên duyệt.'),
      ],
    );
  }
}
