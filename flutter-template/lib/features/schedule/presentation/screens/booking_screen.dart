import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/router/app_routes.dart';
import '../../../../core/utils/context_extensions.dart';
import '../../../../core/widgets/detail_scaffold.dart';
import '../../../../core/widgets/pema_blocks.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../../patients/domain/models/patient_state.dart';
import '../../../patients/presentation/providers/patients_provider.dart';
import '../widgets/week_strip.dart';

class BookingScreen extends ConsumerWidget {
  const BookingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(selectedProfileProvider);
    final name = profile['name'] as String;
    final id = profile['id'] as String;
    final patient = ref.watch(currentPatientProvider);
    void patch(PatientState Function(PatientState) change) =>
        ref.read(patientsProvider.notifier).update(id, change);
    void toast(String message) => context.toast(message);
    return DetailScaffold(
      title: AppRoutes.booking,
      children: [
        heading(name, 'Chọn ngày và giờ trước khi xác nhận'),
        const WeekStrip(),
        tile(
          patient.day,
          'Chạm để đổi ngày',
          Icons.calendar_today_outlined,
          () async {
            final d = await showDatePicker(
              context: context,
              initialDate: DateTime(2026, 9, 22),
              firstDate: DateTime(2026, 9, 22),
              lastDate: DateTime(2027),
            );
            if (d != null)
              patch((p) => p.copyWith(day: '${d.day}/${d.month}/${d.year}'));
          },
        ),
        notice(
          'BS. Tâm · Khám da liễu · 30 phút\n09:00 đã có lịch, không thể chọn.',
        ),
        Wrap(
          spacing: 8,
          children: ['09:00', '10:30', '11:00', '14:00', '15:30']
              .map(
                (t) => ChoiceChip(
                  label: Text(t),
                  selected: patient.appointment == t,
                  onSelected: t == '09:00'
                      ? null
                      : (_) => patch((p) => p.copyWith(appointment: t)),
                ),
              )
              .toList(),
        ),
        primary('Xác nhận lịch', () {
          patch((p) => p.copyWith(confirmed: true));
          toast('Đã lưu lịch ${patient.appointment} · ${patient.day}');
          Navigator.pop(context);
        }),
      ],
    );
  }
}
