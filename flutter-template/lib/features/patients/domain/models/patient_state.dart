import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../catalog/domain/models/patient_profile.dart';
import 'cart_line.dart';

part 'patient_state.freezed.dart';

/// Session-only clinical, schedule, care and cart state for one patient.
@freezed
abstract class PatientState with _$PatientState {
  const PatientState._();

  const factory PatientState({
    required int sessions,
    required String appointment,
    required String day,
    @Default(false) bool checkedIn,
    @Default(false) bool confirmed,
    @Default(false) bool acknowledged,
    @Default('') String note,
    @Default('') String response,
    @Default('') String careNote,
    @Default('Chưa liên hệ') String careStatus,
    String? editingOrder,
    @Default([]) List<CartLine> cart,
    @Default([]) List<String> updates,

    /// Local paths of progress photos the patient sent, oldest first.
    @Default([]) List<String> photos,

    /// Internal CSKH hand-offs; never shown in Care.
    @Default([]) List<String> escalations,
  }) = _PatientState;

  factory PatientState.fromProfile(PatientProfile profile) => PatientState(
    sessions: profile.sessions,
    appointment: profile.appointment,
    day: profile.day,
  );

  int get cartTotal => cart.fold(0, (sum, line) => sum + line.total);
  bool get cartReady =>
      cart.isNotEmpty &&
      cart.every((l) => l.route != 'UNRESOLVED' && l.usage.trim().isNotEmpty);
}
