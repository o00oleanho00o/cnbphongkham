import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../catalog/domain/models/product.dart';
import '../../../catalog/presentation/providers/catalog_provider.dart';
import '../../../session/presentation/providers/session_provider.dart';
import '../../domain/models/cart_line.dart';
import '../../domain/models/patient_state.dart';

part 'patients_provider.g.dart';

@Riverpod(keepAlive: true)
class PatientsNotifier extends _$PatientsNotifier {
  @override
  Map<String, PatientState> build() => const {};

  PatientState of(String id) =>
      state[id] ??
      PatientState.fromProfile(ref.read(catalogProvider).profile(id));

  void update(String id, PatientState Function(PatientState) change) =>
      state = {...state, id: change(of(id))};

  void addToCart(String id, Product product) => update(id, (p) {
    final index = p.cart.indexWhere((l) => l.code == product.code);
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
