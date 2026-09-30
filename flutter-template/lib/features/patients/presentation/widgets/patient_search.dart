import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/widgets/pema_blocks.dart';
import '../../../catalog/presentation/providers/catalog_provider.dart';
import '../../../session/presentation/providers/session_provider.dart';

class PatientSearch extends ConsumerStatefulWidget {
  final VoidCallback onOpen;
  const PatientSearch({super.key, required this.onOpen});
  @override
  ConsumerState<PatientSearch> createState() => _PatientSearchState();
}

class _PatientSearchState extends ConsumerState<PatientSearch> {
  String query = '';
  @override
  Widget build(BuildContext context) {
    final profiles = ref.watch(catalogProvider).profiles;
    final session = ref.watch(sessionProvider);
    return Column(
      children: [
        TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search),
            hintText: 'Tìm tên hoặc mã hồ sơ',
          ),
          onChanged: (v) => setState(() => query = v.toLowerCase()),
        ),
        const SizedBox(height: 16),
        for (int i = 0; i < profiles.length; i++)
          if (session.owns(profiles[i]) &&
              (profiles[i].matches(query) ||
                  'p${(i + 1).toString().padLeft(3, '0')}'.contains(query)))
            tile(
              profiles[i].name,
              'P${(i + 1).toString().padLeft(3, '0')} · Đang điều trị',
              Icons.person_outline,
              () {
                ref.read(sessionProvider.notifier).select(i);
                widget.onOpen();
              },
            ),
      ],
    );
  }
}
