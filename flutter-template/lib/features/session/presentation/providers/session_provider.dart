import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../catalog/domain/models/patient_profile.dart';
import '../../../catalog/presentation/providers/catalog_provider.dart';
import '../../domain/models/session.dart';

part 'session_provider.g.dart';

@Riverpod(keepAlive: true)
class SessionNotifier extends _$SessionNotifier {
  @override
  Session build() => const Session();

  void select(int index) => state = state.careMode
      ? state.copyWith(careSelected: index)
      : state.copyWith(staffSelected: index);

  void enterCare() => state = state.copyWith(careMode: true);

  void enterStaff(String role, String name) {
    var next = state.copyWith(
      careMode: false,
      staffRole: role,
      staffName: name,
      staffDoctor: name,
    );
    final profiles = ref.read(catalogProvider).profiles;
    if (!next.owns(profiles[next.staffSelected])) {
      next = next.copyWith(
        staffSelected: profiles.indexWhere((p) => p.doctor == next.staffDoctor),
      );
    }
    state = next;
  }
}

@riverpod
PatientProfile selectedProfile(Ref ref) {
  final index = ref.watch(sessionProvider.select((s) => s.selected));
  return ref.watch(catalogProvider).profiles[index];
}

@riverpod
String selectedPatientId(Ref ref) =>
    ref.watch(selectedProfileProvider.select((p) => p.id));
