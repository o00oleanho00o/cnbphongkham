import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'catalog.dart';
import 'patients.dart';
import 'session.dart';

part 'orders.g.dart';

class Order {
  const Order({
    required this.id,
    required this.patientId,
    required this.patientName,
    required this.approved,
    required this.items,
  });

  final String id, patientId, patientName;
  final bool approved;
  final List<CartLine> items;

  int get total => items.fold(0, (sum, line) => sum + line.total);
}

@Riverpod(keepAlive: true)
class OrdersNotifier extends _$OrdersNotifier {
  @override
  List<Order> build() => const [];

  /// Moves the patient's cart into a draft or approved order and clears it.
  void save(String patientId, {required bool approve}) {
    final patients = ref.read(patientsProvider.notifier);
    final patient = patients.of(patientId);
    if (patient.cart.isEmpty || (approve && !patient.cartReady)) {
      throw StateError('Cần phân loại và nhập hướng dẫn trước khi duyệt');
    }
    final existing = state.indexWhere((o) => o.id == patient.editingOrder);
    final order = Order(
      id: patient.editingOrder ?? 'DN-${state.length + 1}',
      patientId: patientId,
      patientName:
          ref.read(catalogProvider).profile(patientId)['name'] as String,
      approved: approve,
      items: patient.cart,
    );
    state = existing < 0
        ? [...state, order]
        : [
            for (var i = 0; i < state.length; i++)
              i == existing ? order : state[i],
          ];
    patients.update(
      patientId,
      (p) => p.copyWith(cart: const [], editingOrder: null),
    );
  }

  void edit(String patientId, Order order) => ref
      .read(patientsProvider.notifier)
      .update(
        patientId,
        (p) => p.copyWith(cart: order.items, editingOrder: order.id),
      );
}

@riverpod
List<Order> patientOrders(Ref ref, String id) =>
    ref.watch(ordersProvider).where((o) => o.patientId == id).toList();

@riverpod
List<Order> currentOrders(Ref ref) =>
    ref.watch(patientOrdersProvider(ref.watch(selectedPatientIdProvider)));

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
