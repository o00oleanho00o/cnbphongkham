abstract interface class FinanceRepository {
  /// Role-scoped finance projection for [month] (`yyyy-MM`).
  Future<Map<String, dynamic>> getState({
    required String month,
    required String role,
    required String doctor,
  });

  /// Throws with the server's error message when the command is rejected.
  Future<void> sendCommand(
    String action,
    Map<String, dynamic> body, {
    required String role,
    required String doctor,
  });
}
