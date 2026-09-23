// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'orders.dart';

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

@ProviderFor(patientOrders)
final patientOrdersProvider = PatientOrdersFamily._();

final class PatientOrdersProvider
    extends $FunctionalProvider<List<Order>, List<Order>, List<Order>>
    with $Provider<List<Order>> {
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
  $ProviderElement<List<Order>> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  List<Order> create(Ref ref) {
    final argument = this.argument as String;
    return patientOrders(ref, argument);
  }

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

String _$patientOrdersHash() => r'81e4d4972de5fbaa4d039d63202c73ac111ad40a';

final class PatientOrdersFamily extends $Family
    with $FunctionalFamilyOverride<List<Order>, String> {
  PatientOrdersFamily._()
    : super(
        retry: null,
        name: r'patientOrdersProvider',
        dependencies: null,
        $allTransitiveDependencies: null,
        isAutoDispose: true,
      );

  PatientOrdersProvider call(String id) =>
      PatientOrdersProvider._(argument: id, from: this);

  @override
  String toString() => r'patientOrdersProvider';
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

/// Demo cash totals per patient; no ledger or bank connection.

@ProviderFor(ReceiptsNotifier)
final receiptsProvider = ReceiptsNotifierProvider._();

/// Demo cash totals per patient; no ledger or bank connection.
final class ReceiptsNotifierProvider
    extends $NotifierProvider<ReceiptsNotifier, Map<String, int>> {
  /// Demo cash totals per patient; no ledger or bank connection.
  ReceiptsNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'receiptsProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$receiptsNotifierHash();

  @$internal
  @override
  ReceiptsNotifier create() => ReceiptsNotifier();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(Map<String, int> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<Map<String, int>>(value),
    );
  }
}

String _$receiptsNotifierHash() => r'44d32d8d9e7efcdaee59be55d4d7f88ccfc6581e';

/// Demo cash totals per patient; no ledger or bank connection.

abstract class _$ReceiptsNotifier extends $Notifier<Map<String, int>> {
  Map<String, int> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<Map<String, int>, Map<String, int>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<Map<String, int>, Map<String, int>>,
              Map<String, int>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}

@ProviderFor(currentPaid)
final currentPaidProvider = CurrentPaidProvider._();

final class CurrentPaidProvider extends $FunctionalProvider<int, int, int>
    with $Provider<int> {
  CurrentPaidProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'currentPaidProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$currentPaidHash();

  @$internal
  @override
  $ProviderElement<int> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  int create(Ref ref) {
    return currentPaid(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(int value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<int>(value),
    );
  }
}

String _$currentPaidHash() => r'3e9f5bb81fbfbf2fcceb3b4cf238c3ef4e408869';
