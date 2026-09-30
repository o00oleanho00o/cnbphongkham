abstract final class ApiConfig {
  /// Override with `--dart-define=PEMA_FINANCE_API=http://host:port`.
  static const financeBaseUrl = String.fromEnvironment(
    'PEMA_FINANCE_API',
    defaultValue: 'http://127.0.0.1:4174',
  );
}
