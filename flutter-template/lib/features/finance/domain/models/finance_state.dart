import 'package:freezed_annotation/freezed_annotation.dart';

import '../repositories/finance_repository.dart';
import 'finance_snapshot.dart';

part 'finance_state.freezed.dart';

/// Current month in Vietnam time (UTC+7), e.g. `2026-09`.
String financeMonth() => DateTime.now()
    .toUtc()
    .add(const Duration(hours: 7))
    .toIso8601String()
    .substring(0, 7);

/// Value equality lets Riverpod skip polls that return the same projection.
@freezed
abstract class FinanceState with _$FinanceState {
  const FinanceState._();

  const factory FinanceState({
    required String month,
    @Default('owner') String role,
    @Default('D0') String doctor,
    @Default('') String error,

    /// Null until the first load and right after a role switch.
    FinanceSnapshot? data,
    @Default(false) bool sending,
  }) = _FinanceState;

  FinanceActor get actor => (role: role, doctor: doctor);
  bool get private => role == 'doctor';
  int get unread => data?.unread ?? 0;
}
