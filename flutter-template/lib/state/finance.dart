import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:http/http.dart' as http;
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'finance.g.dart';

const financeApi = String.fromEnvironment(
  'PEMA_FINANCE_API',
  defaultValue: 'http://127.0.0.1:4174',
);
const _keep = Object();

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
  final Map<String, dynamic>? data;
  final bool sending;

  int get unread => (data?['notifications'] as List? ?? [])
      .where((n) => n['read'] == false)
      .length;

  Map<String, String> get headers => {
    'Content-Type': 'application/json',
    'X-Pema-Role': role,
    'X-Pema-Doctor': doctor,
  };

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

@Riverpod(keepAlive: true)
http.Client financeClient(Ref ref) {
  final client = http.Client();
  ref.onDispose(client.close);
  return client;
}

/// Off by default so layout tests never reach the finance API.
@Riverpod(keepAlive: true)
bool financeEnabled(Ref ref) => false;

@Riverpod(keepAlive: true)
class FinanceNotifier extends _$FinanceNotifier {
  Timer? _timer;
  AppLifecycleListener? _lifecycle;
  int _generation = 0;
  bool _loading = false, _foreground = true;

  http.Client get _client => ref.read(financeClientProvider);

  @override
  FinanceState build() {
    ref.onDispose(() {
      _generation++;
      _timer?.cancel();
      _lifecycle?.dispose();
    });
    return FinanceState(month: financeMonth());
  }

  /// Polls while the app is in the foreground.
  void start() {
    _lifecycle ??= AppLifecycleListener(
      onStateChange: (value) {
        _foreground = value == AppLifecycleState.resumed;
        if (_foreground) refresh();
      },
    );
    refresh();
    _timer ??= Timer.periodic(const Duration(seconds: 4), (_) {
      if (_foreground && !_loading && !state.sending) refresh();
    });
  }

  Future<void> refresh() async {
    final token = ++_generation;
    _loading = true;
    try {
      final response = await _client
          .get(
            Uri.parse('$financeApi/state?month=${state.month}'),
            headers: state.headers,
          )
          .timeout(const Duration(seconds: 7));
      if (token != _generation) return;
      final value = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode != 200) throw Exception(value['error']);
      state = state.copyWith(data: value, error: '');
    } catch (_) {
      if (token == _generation) {
        state = state.copyWith(
          error: 'Chưa kết nối dữ liệu tài chính. Kiểm tra dịch vụ và thử lại.',
        );
      }
    } finally {
      if (token == _generation) _loading = false;
    }
  }

  /// Switching role drops the previous role's private projection first.
  void select(String value) {
    final bits = value.split(':');
    _generation++;
    state = state.copyWith(role: bits[0], doctor: bits[1], data: null);
    refresh();
  }

  Future<void> setMonth(String month) {
    state = state.copyWith(month: month);
    return refresh();
  }

  Future<bool> command(String action, Map<String, dynamic> value) async {
    if (state.sending) return false;
    state = state.copyWith(sending: true);
    try {
      final response = await _client
          .post(
            Uri.parse('$financeApi/command/$action'),
            headers: state.headers,
            body: jsonEncode(value),
          )
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) {
        throw Exception((jsonDecode(response.body) as Map)['error']);
      }
      state = state.copyWith(error: '');
      await refresh();
      return true;
    } catch (e) {
      if (ref.mounted) {
        state = state.copyWith(
          error: e.toString().replaceFirst('Exception: ', ''),
        );
      }
      return false;
    } finally {
      if (ref.mounted) state = state.copyWith(sending: false);
    }
  }
}
