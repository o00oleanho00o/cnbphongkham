import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_navigation.dart';
import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/context_extensions.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/domain/models/patient_state.dart';
import '../../../patients/presentation/providers/patients_provider.dart';

class CustomerCareContactScreen extends ConsumerStatefulWidget {
  const CustomerCareContactScreen({super.key});

  @override
  ConsumerState<CustomerCareContactScreen> createState() =>
      _CustomerCareContactScreenState();
}

class _CustomerCareContactScreenState
    extends ConsumerState<CustomerCareContactScreen> {
  final text = TextEditingController();

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(selectedProfileProvider);
    final name = profile['name'] as String;
    final id = profile['id'] as String;
    final patient = ref.watch(currentPatientProvider);
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void open(String route) => context.openRoute(route);
    void toast(String message) => context.toast(message);
    return DetailScaffold(
      title: AppRoutes.customerCare,
      children: [
        heading(name, '${id} · ${profile['case']}'),
        notice('Nội dung liên hệ nội bộ không hiển thị cho người bệnh.'),
        if (patient.careNote.isNotEmpty) notice(patient.careNote),
        TextField(
          controller: text,
          maxLines: 3,
          decoration: const InputDecoration(
            labelText: 'Kết quả liên hệ / việc cần bàn giao',
          ),
        ),
        primary('Lưu kết quả liên hệ', () {
          if (text.text.trim().isEmpty) {
            toast('Nhập kết quả liên hệ');
            return;
          }
          patch(
            (p) => p.copyWith(
              careNote: text.text.trim(),
              careStatus: 'Đã liên hệ',
            ),
          );
          toast('Đã lưu ghi chú nội bộ');
        }),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(
            minimumSize: const Size.fromHeight(48),
            backgroundColor: Colors.white,
            side: const BorderSide(color: Color(0xFFCADBE8)),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
          ),
          onPressed: () => open(AppRoutes.booking),
          icon: const Icon(Icons.calendar_month_outlined),
          label: const Text('Hỗ trợ đặt lại lịch'),
        ),
        TextButton.icon(
          icon: const Icon(Icons.forward_to_inbox_outlined),
          label: const Text('Chuyển bác sĩ xem'),
          onPressed: () {
            if (text.text.trim().isEmpty) {
              toast('Nhập nội dung cần bác sĩ xem');
              return;
            }
            patch(
              (p) => p.copyWith(
                careNote: text.text.trim(),
                careStatus: 'Chờ bác sĩ',
                escalations: [...p.escalations, text.text.trim()],
              ),
            );
            toast('Đã chuyển vào hàng chờ bác sĩ');
          },
        ),
      ],
    );
  }
}
