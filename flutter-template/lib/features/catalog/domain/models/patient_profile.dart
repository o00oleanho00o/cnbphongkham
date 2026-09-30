import 'package:freezed_annotation/freezed_annotation.dart';

part 'patient_profile.freezed.dart';

/// A CRM follow-up attached to a profile, e.g. `d7` or `due`.
@freezed
abstract class CareTask with _$CareTask {
  const factory CareTask({
    required String id,
    required String type,
    required String title,
    required String status,
  }) = _CareTask;
}

/// Synthetic patient profile from the bundled catalog.
@freezed
abstract class PatientProfile with _$PatientProfile {
  const PatientProfile._();

  const factory PatientProfile({
    required String id,
    required String name,
    required String doctor,
    required int sessions,
    required int totalSessions,
    required String appointment,
    required String day,

    /// CSKH group key (`d1`, `due`, ...); empty when not in the care queue.
    required String careGroup,

    /// Human label of [careGroup] shown in account pickers.
    required String caseLabel,
    @Default([]) List<CareTask> tasks,
  }) = _PatientProfile;

  bool get inCareQueue => careGroup.isNotEmpty;

  bool hasTask(String type) => tasks.any((t) => t.type == type);

  /// Case-insensitive match on name; [query] must be lower-case.
  bool matches(String query) => name.toLowerCase().contains(query);

  /// Up to two initials from the given names, e.g. "Nguyễn Minh Linh" → "ML".
  String get initials => name
      .split(' ')
      .skip(1)
      .toList()
      .reversed
      .take(2)
      .toList()
      .reversed
      .map((v) => v[0])
      .join();
}
