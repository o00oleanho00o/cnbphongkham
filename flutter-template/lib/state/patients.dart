import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'catalog.dart';
import 'session.dart';

part 'patients.g.dart';

const _keep = Object();

class CartLine {
  const CartLine({
    required this.product,
    required this.route,
    this.quantity = 1,
    this.usage = '',
  });

  CartLine.of(Map<String, dynamic> product)
    : this(product: product, route: product['outputType'] as String);

  final Map<String, dynamic> product;
  final int quantity;
  final String usage, route;

  String get code => product['code'] as String;
  String get name => product['name'] as String;
  String get unit => product['unit'] as String;
  int get total => ((product['price'] as num) * quantity).round();

  CartLine copyWith({int? quantity, String? usage, String? route}) => CartLine(
    product: product,
    quantity: quantity ?? this.quantity,
    usage: usage ?? this.usage,
    route: route ?? this.route,
  );
}

/// Session-only clinical, schedule, care and cart state for one patient.
class PatientState {
  const PatientState({
    required this.sessions,
    required this.appointment,
    required this.day,
    this.checkedIn = false,
    this.confirmed = false,
    this.acknowledged = false,
    this.note = '',
    this.response = '',
    this.careNote = '',
    this.careStatus = 'Chưa liên hệ',
    this.editingOrder,
    this.cart = const [],
    this.updates = const [],
    this.escalations = const [],
  });

  PatientState.fromProfile(Map<String, dynamic> profile)
    : this(
        sessions: profile['sessions'] as int,
        appointment: profile['appointment'] as String,
        day: profile['day'] as String,
      );

  final int sessions;
  final String appointment, day;
  final bool checkedIn, confirmed, acknowledged;
  final String note, response, careNote, careStatus;
  final String? editingOrder;
  final List<CartLine> cart;
  final List<String> updates;

  /// Internal CSKH hand-offs; never shown in Care.
  final List<String> escalations;

  int get cartTotal => cart.fold(0, (sum, line) => sum + line.total);
  bool get cartReady =>
      cart.isNotEmpty &&
      cart.every((l) => l.route != 'UNRESOLVED' && l.usage.trim().isNotEmpty);

  PatientState copyWith({
    int? sessions,
    String? appointment,
    String? day,
    bool? checkedIn,
    bool? confirmed,
    bool? acknowledged,
    String? note,
    String? response,
    String? careNote,
    String? careStatus,
    Object? editingOrder = _keep,
    List<CartLine>? cart,
    List<String>? updates,
    List<String>? escalations,
  }) => PatientState(
    sessions: sessions ?? this.sessions,
    appointment: appointment ?? this.appointment,
    day: day ?? this.day,
    checkedIn: checkedIn ?? this.checkedIn,
    confirmed: confirmed ?? this.confirmed,
    acknowledged: acknowledged ?? this.acknowledged,
    note: note ?? this.note,
    response: response ?? this.response,
    careNote: careNote ?? this.careNote,
    careStatus: careStatus ?? this.careStatus,
    editingOrder: identical(editingOrder, _keep)
        ? this.editingOrder
        : editingOrder as String?,
    cart: cart ?? this.cart,
    updates: updates ?? this.updates,
    escalations: escalations ?? this.escalations,
  );
}

@Riverpod(keepAlive: true)
class PatientsNotifier extends _$PatientsNotifier {
  @override
  Map<String, PatientState> build() => const {};

  PatientState of(String id) =>
      state[id] ??
      PatientState.fromProfile(ref.read(catalogProvider).profile(id));

  void update(String id, PatientState Function(PatientState) change) =>
      state = {...state, id: change(of(id))};

  void addToCart(String id, Map<String, dynamic> product) => update(id, (p) {
    final index = p.cart.indexWhere((l) => l.code == product['code']);
    if (index < 0) return p.copyWith(cart: [...p.cart, CartLine.of(product)]);
    return p.copyWith(
      cart: [
        for (var i = 0; i < p.cart.length; i++)
          i == index
              ? p.cart[i].copyWith(quantity: p.cart[i].quantity + 1)
              : p.cart[i],
      ],
    );
  });

  void updateLine(String id, int index, CartLine Function(CartLine) change) =>
      update(
        id,
        (p) => p.copyWith(
          cart: [
            for (var i = 0; i < p.cart.length; i++)
              i == index ? change(p.cart[i]) : p.cart[i],
          ],
        ),
      );

  void removeLine(String id, int index) =>
      update(id, (p) => p.copyWith(cart: [...p.cart]..removeAt(index)));
}

@riverpod
PatientState patientState(Ref ref, String id) =>
    ref.watch(patientsProvider.select((all) => all[id])) ??
    PatientState.fromProfile(ref.watch(catalogProvider).profile(id));

@riverpod
PatientState currentPatient(Ref ref) =>
    ref.watch(patientStateProvider(ref.watch(selectedPatientIdProvider)));
