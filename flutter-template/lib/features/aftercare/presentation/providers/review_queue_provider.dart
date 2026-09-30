import 'package:flutter/foundation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../catalog/domain/models/patient_profile.dart';
import '../../../catalog/presentation/providers/catalog_provider.dart';
import '../../../patients/presentation/providers/patients_provider.dart';
import '../../../session/presentation/providers/session_provider.dart';

part 'review_queue_provider.g.dart';

/// Owned profiles that need a doctor's review: a D+7 task, a patient update
/// or a CSKH escalation. Unrelated edits produce an equal list, so
/// `updateShouldNotify` keeps the workspace from rebuilding.
@riverpod
class ReviewQueue extends _$ReviewQueue {
  @override
  List<PatientProfile> build() {
    final session = ref.watch(sessionProvider);
    final states = ref.watch(patientsProvider);
    return [
      for (final p in ref.watch(catalogProvider).profiles)
        if (session.owns(p) &&
            (p.hasTask('d7') ||
                (states[p.id]?.updates.isNotEmpty ?? false) ||
                (states[p.id]?.escalations.isNotEmpty ?? false)))
          p,
    ];
  }

  @override
  bool updateShouldNotify(
    List<PatientProfile> previous,
    List<PatientProfile> next,
  ) => !listEquals(previous, next);
}
