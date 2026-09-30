import 'package:flutter/foundation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../catalog/presentation/providers/catalog_provider.dart';
import '../../../patients/presentation/providers/patients_provider.dart';
import '../../domain/models/care_case.dart';

part 'care_queue_provider.g.dart';

/// Profiles in the CSKH queue with their contact status. Cart edits produce an
/// equal list, so `updateShouldNotify` keeps the queue from rebuilding.
@riverpod
class CareCases extends _$CareCases {
  @override
  List<CareCase> build() {
    final states = ref.watch(patientsProvider);
    return [
      for (final p in ref.watch(catalogProvider).profiles)
        if (p.inCareQueue)
          CareCase(
            profile: p,
            status: states[p.id]?.careStatus ?? careNotContacted,
          ),
    ];
  }

  @override
  bool updateShouldNotify(List<CareCase> previous, List<CareCase> next) =>
      !listEquals(previous, next);
}
