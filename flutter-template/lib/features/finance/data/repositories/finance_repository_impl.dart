import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/repositories/finance_repository.dart';
import '../datasources/finance_remote_data_source.dart';

part 'finance_repository_impl.g.dart';

class FinanceRepositoryImpl implements FinanceRepository {
  const FinanceRepositoryImpl(this._remote);

  final FinanceRemoteDataSource _remote;

  @override
  Future<Map<String, dynamic>> getState({
    required String month,
    required String role,
    required String doctor,
  }) => _remote.fetchState(month: month, role: role, doctor: doctor);

  @override
  Future<void> sendCommand(
    String action,
    Map<String, dynamic> body, {
    required String role,
    required String doctor,
  }) => _remote.postCommand(action, body, role: role, doctor: doctor);
}

@Riverpod(keepAlive: true)
FinanceRepository financeRepository(Ref ref) =>
    FinanceRepositoryImpl(ref.watch(financeRemoteDataSourceProvider));
