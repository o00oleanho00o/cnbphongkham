const _keep = Object();

/// Current month in Vietnam time (UTC+7), e.g. `2026-09`.
String financeMonth() => DateTime.now()
    .toUtc()
    .add(const Duration(hours: 7))
    .toIso8601String()
    .substring(0, 7);

class FinanceState {
  const FinanceState({
    required this.month,
    this.role = 'owner',
    this.doctor = 'D0',
    this.error = '',
    this.data,
    this.sending = false,
  });

  final String role, doctor, month, error;

  /// Role-scoped projection returned by the finance API.
  final Map<String, dynamic>? data;
  final bool sending;

  int get unread => (data?['notifications'] as List? ?? [])
      .where((n) => n['read'] == false)
      .length;

  FinanceState copyWith({
    String? role,
    String? doctor,
    String? month,
    String? error,
    Object? data = _keep,
    bool? sending,
  }) => FinanceState(
    role: role ?? this.role,
    doctor: doctor ?? this.doctor,
    month: month ?? this.month,
    error: error ?? this.error,
    data: identical(data, _keep) ? this.data : data as Map<String, dynamic>?,
    sending: sending ?? this.sending,
  );
}
