// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'orders_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(OrdersNotifier)
final ordersProvider = OrdersNotifierProvider._();

final class OrdersNotifierProvider
    extends $NotifierProvider<OrdersNotifier, List<Order>> {
  OrdersNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'ordersProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$ordersNotifierHash();

  @$internal
  @override
  OrdersNotifier create() => OrdersNotifier();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<Order> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<Order>>(value),
    );
  }
}

String _$ordersNotifierHash() => r'204c5fd7a2d89b88708e07ffd525d87527e5933c';

abstract class _$OrdersNotifier extends $Notifier<List<Order>> {
  List<Order> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<List<Order>, List<Order>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<List<Order>, List<Order>>,
              List<Order>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}

/// Orders of one patient. Saving another patient's order produces an equal
/// list here, so `updateShouldNotify` keeps this patient's screens still.

@ProviderFor(PatientOrders)
final patientOrdersProvider = PatientOrdersFamily._();

/// Orders of one patient. Saving another patient's order produces an equal
/// list here, so `updateShouldNotify` keeps this patient's screens still.
final class PatientOrdersProvider
    extends $NotifierProvider<PatientOrders, List<Order>> {
  /// Orders of one patient. Saving another patient's order produces an equal
  /// list here, so `updateShouldNotify` keeps this patient's screens still.
  PatientOrdersProvider._({
    required PatientOrdersFamily super.from,
    required String super.argument,
  }) : super(
         retry: null,
         name: r'patientOrdersProvider',
         isAutoDispose: true,
         dependencies: null,
         $allTransitiveDependencies: null,
       );

  @override
  String debugGetCreateSourceHash() => _$patientOrdersHash();

  @override
  String toString() {
    return r'patientOrdersProvider'
        ''
        '($argument)';
  }

  @$internal
  @override
  PatientOrders create() => PatientOrders();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<Order> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<Order>>(value),
    );
  }

  @override
  bool operator ==(Object other) {
    return other is PatientOrdersProvider && other.argument == argument;
  }

  @override
  int get hashCode {
    return argument.hashCode;
  }
}

String _$patientOrdersHash() => r'3c02969cac8d4cb0ba96b931116a12391e79fcb0';

/// Orders of one patient. Saving another patient's order produces an equal
/// list here, so `updateShouldNotify` keeps this patient's screens still.

final class PatientOrdersFamily extends $Family
    with
        $ClassFamilyOverride<
          PatientOrders,
          List<Order>,
          List<Order>,
          List<Order>,
          String
        > {
  PatientOrdersFamily._()
    : super(
        retry: null,
        name: r'patientOrdersProvider',
        dependencies: null,
        $allTransitiveDependencies: null,
        isAutoDispose: true,
      );

  /// Orders of one patient. Saving another patient's order produces an equal
  /// list here, so `updateShouldNotify` keeps this patient's screens still.

  PatientOrdersProvider call(String id) =>
      PatientOrdersProvider._(argument: id, from: this);

  @override
  String toString() => r'patientOrdersProvider';
}

/// Orders of one patient. Saving another patient's order produces an equal
/// list here, so `updateShouldNotify` keeps this patient's screens still.

abstract class _$PatientOrders extends $Notifier<List<Order>> {
  late final _$args = ref.$arg as String;
  String get id => _$args;

  List<Order> build(String id);
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<List<Order>, List<Order>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<List<Order>, List<Order>>,
              List<Order>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, () => build(_$args));
  }
}

@ProviderFor(currentOrders)
final currentOrdersProvider = CurrentOrdersProvider._();

final class CurrentOrdersProvider
    extends $FunctionalProvider<List<Order>, List<Order>, List<Order>>
    with $Provider<List<Order>> {
  CurrentOrdersProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'currentOrdersProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$currentOrdersHash();

  @$internal
  @override
  $ProviderElement<List<Order>> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  List<Order> create(Ref ref) {
    return currentOrders(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<Order> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<Order>>(value),
    );
  }
}

String _$currentOrdersHash() => r'c08b067ff026a448cba774f43e31a1b61c5b6d85';
