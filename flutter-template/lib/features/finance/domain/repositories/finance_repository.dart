import '../models/finance_snapshot.dart';
import '../models/procedure_entry.dart';

/// Demo role headers sent with every request; not authentication.
typedef FinanceActor = ({String role, String doctor});

/// Commands throw with the server's error message when rejected.
abstract interface class FinanceRepository {
  /// Role-scoped finance projection for [month] (`yyyy-MM`).
  Future<FinanceSnapshot> getState(String month, FinanceActor actor);

  Future<void> approveEntry(String id, FinanceActor actor);

  Future<void> voidEntry(String id, String reason, FinanceActor actor);

  Future<void> recordEntry(ProcedureEntry entry, FinanceActor actor);

  /// [key] makes retries idempotent on the server.
  Future<void> recordPayment({
    required String key,
    required String invoice,
    required int amount,
    required String method,
    required FinanceActor actor,
  });

  Future<void> closePeriod(String month, FinanceActor actor);

  Future<void> markPeriodPaid(
    String month,
    String reference,
    FinanceActor actor,
  );

  /// [rate] in basis points; [basis] is `net`, `list` or `collected`.
  Future<void> updateRate({
    required String service,
    required int rate,
    required String basis,
    required FinanceActor actor,
  });

  Future<void> markNotificationRead(String id, FinanceActor actor);
}
