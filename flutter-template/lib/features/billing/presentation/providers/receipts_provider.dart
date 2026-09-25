import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../orders/presentation/providers/orders_provider.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../domain/models/bill.dart';

part 'receipts_provider.g.dart';

/// Demo cash totals per patient; no ledger or bank connection.
@Riverpod(keepAlive: true)
class ReceiptsNotifier extends _$ReceiptsNotifier {
  @override
  Map<String, int> build() => const {};

  void settle(String patientId, int total) =>
      state = {...state, patientId: total};
}

@riverpod
int currentPaid(Ref ref) =>
    ref.watch(receiptsProvider)[ref.watch(selectedPatientIdProvider)] ?? 0;

@riverpod
Bill currentBill(Ref ref) => Bill(
  total: ref.watch(currentOrdersProvider).fold(0, (n, o) => n + o.total),
  paid: ref.watch(currentPaidProvider),
);
