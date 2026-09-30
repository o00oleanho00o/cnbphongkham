import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/finance_repository_impl.dart';
import '../../domain/models/finance_state.dart';
import '../../domain/models/procedure_entry.dart';
import '../../domain/repositories/finance_repository.dart';

part 'finance_provider.g.dart';

/// Off by default so layout tests never reach the finance API.
@Riverpod(keepAlive: true)
bool financeEnabled(Ref ref) => false;

@Riverpod(keepAlive: true)
class FinanceNotifier extends _$FinanceNotifier {
  Timer? _timer;
  AppLifecycleListener? _lifecycle;
  int _generation = 0;
  bool _loading = false, _foreground = true;

  FinanceRepository get _repository => ref.read(financeRepositoryProvider);

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
      final value = await _repository.getState(state.month, state.actor);
      if (token != _generation) return;
      // An unchanged poll yields an equal state, which Riverpod does not emit.
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

  Future<bool> approveEntry(String id) =>
      _command((a) => _repository.approveEntry(id, a));

  Future<bool> voidEntry(String id, String reason) =>
      _command((a) => _repository.voidEntry(id, reason, a));

  Future<bool> recordEntry(ProcedureEntry entry) =>
      _command((a) => _repository.recordEntry(entry, a));

  Future<bool> recordPayment({
    required String key,
    required String invoice,
    required int amount,
    String method = 'Tiền mặt',
  }) => _command(
    (a) => _repository.recordPayment(
      key: key,
      invoice: invoice,
      amount: amount,
      method: method,
      actor: a,
    ),
  );

  Future<bool> closePeriod() =>
      _command((a) => _repository.closePeriod(state.month, a));

  Future<bool> markPeriodPaid(String reference) =>
      _command((a) => _repository.markPeriodPaid(state.month, reference, a));

  Future<bool> updateRate({
    required String service,
    required int rate,
    required String basis,
  }) => _command(
    (a) => _repository.updateRate(
      service: service,
      rate: rate,
      basis: basis,
      actor: a,
    ),
  );

  Future<bool> markNotificationRead(String id) =>
      _command((a) => _repository.markNotificationRead(id, a));

  /// Runs one command at a time; on success reloads, on failure keeps the
  /// server's message in `state.error`.
  Future<bool> _command(Future<void> Function(FinanceActor actor) send) async {
    if (state.sending) return false;
    state = state.copyWith(sending: true);
    try {
      await send(state.actor);
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
