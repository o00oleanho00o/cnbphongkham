import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/models/finance_snapshot.dart';
import '../../domain/models/procedure_entry.dart';
import '../../domain/repositories/finance_repository.dart';
import '../datasources/finance_remote_data_source.dart';
import '../mappers/finance_mapper.dart';

part 'finance_repository_impl.g.dart';

class FinanceRepositoryImpl implements FinanceRepository {
  const FinanceRepositoryImpl(this._remote);

  final FinanceRemoteDataSource _remote;

  Future<void> _send(
    String action,
    Map<String, dynamic> body,
    FinanceActor a,
  ) => _remote.postCommand(action, body, role: a.role, doctor: a.doctor);

  @override
  Future<FinanceSnapshot> getState(String month, FinanceActor actor) async =>
      FinanceMapper.snapshot(
        await _remote.fetchState(
          month: month,
          role: actor.role,
          doctor: actor.doctor,
        ),
      );

  @override
  Future<void> approveEntry(String id, FinanceActor actor) =>
      _send('approve', {'id': id}, actor);

  @override
  Future<void> voidEntry(String id, String reason, FinanceActor actor) =>
      _send('void', {'id': id, 'reason': reason}, actor);

  @override
  Future<void> recordEntry(ProcedureEntry entry, FinanceActor actor) =>
      _send('entry', FinanceMapper.entry(entry), actor);

  @override
  Future<void> recordPayment({
    required String key,
    required String invoice,
    required int amount,
    required String method,
    required FinanceActor actor,
  }) => _send('payment', {
    'id': key,
    'invoice': invoice,
    'amount': amount,
    'method': method,
  }, actor);

  @override
  Future<void> closePeriod(String month, FinanceActor actor) =>
      _send('close', {'month': month}, actor);

  @override
  Future<void> markPeriodPaid(
    String month,
    String reference,
    FinanceActor actor,
  ) => _send('paid', {'month': month, 'reference': reference}, actor);

  @override
  Future<void> updateRate({
    required String service,
    required int rate,
    required String basis,
    required FinanceActor actor,
  }) =>
      _send('rate', {'service': service, 'rate': rate, 'basis': basis}, actor);

  @override
  Future<void> markNotificationRead(String id, FinanceActor actor) =>
      _send('read', {'id': id}, actor);
}

@Riverpod(keepAlive: true)
FinanceRepository financeRepository(Ref ref) =>
    FinanceRepositoryImpl(ref.watch(financeRemoteDataSourceProvider));
