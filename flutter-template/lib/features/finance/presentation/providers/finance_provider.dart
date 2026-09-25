import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/widgets.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/finance_repository_impl.dart';
import '../../domain/models/finance_state.dart';
import '../../domain/repositories/finance_repository.dart';

part 'finance_provider.g.dart';

const _json = DeepCollectionEquality();

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
      final value = await _repository.getState(
        month: state.month,
        role: state.role,
        doctor: state.doctor,
      );
      if (token != _generation) return;
      // Polling usually returns the same projection; skip the emit so
      // watchers don't rebuild every 4 seconds.
      if (state.error.isEmpty && _json.equals(state.data, value)) return;
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
      await _repository.sendCommand(
        action,
        value,
        role: state.role,
        doctor: state.doctor,
      );
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
