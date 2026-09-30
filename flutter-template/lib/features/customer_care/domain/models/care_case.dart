import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../catalog/domain/models/patient_profile.dart';

part 'care_case.freezed.dart';

/// Contact status of a case before staff has logged anything.
const careNotContacted = 'Chưa liên hệ';

/// One profile in the CSKH queue together with its current contact status.
@freezed
abstract class CareCase with _$CareCase {
  const CareCase._();

  const factory CareCase({
    required PatientProfile profile,
    @Default(careNotContacted) String status,
  }) = _CareCase;

  bool inGroup(String group) => group == 'all' || profile.careGroup == group;

  bool matches(String query) =>
      '${profile.id} ${profile.name}'.toLowerCase().contains(query);
}
