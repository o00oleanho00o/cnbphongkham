// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'receipts_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
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

@ProviderFor(currentBill)
final currentBillProvider = CurrentBillProvider._();

final class CurrentBillProvider extends $FunctionalProvider<Bill, Bill, Bill>
    with $Provider<Bill> {
  CurrentBillProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'currentBillProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$currentBillHash();

  @$internal
  @override
  $ProviderElement<Bill> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  Bill create(Ref ref) {
    return currentBill(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(Bill value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<Bill>(value),
    );
  }
}

String _$currentBillHash() => r'c0c7c8ea4fd60bad8fabfd0efe317b3917a0b13a';
