// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'finance.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(financeClient)
final financeClientProvider = FinanceClientProvider._();

final class FinanceClientProvider
    extends $FunctionalProvider<http.Client, http.Client, http.Client>
    with $Provider<http.Client> {
  FinanceClientProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'financeClientProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$financeClientHash();

  @$internal
  @override
  $ProviderElement<http.Client> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  http.Client create(Ref ref) {
    return financeClient(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(http.Client value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<http.Client>(value),
    );
  }
}

String _$financeClientHash() => r'f3d5c9ef9a8dabb889db3d4700a0a4667955f59b';

/// Off by default so layout tests never reach the finance API.

@ProviderFor(financeEnabled)
final financeEnabledProvider = FinanceEnabledProvider._();

/// Off by default so layout tests never reach the finance API.

final class FinanceEnabledProvider extends $FunctionalProvider<bool, bool, bool>
    with $Provider<bool> {
  /// Off by default so layout tests never reach the finance API.
  FinanceEnabledProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'financeEnabledProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$financeEnabledHash();

  @$internal
  @override
  $ProviderElement<bool> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  bool create(Ref ref) {
    return financeEnabled(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(bool value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<bool>(value),
    );
  }
}

String _$financeEnabledHash() => r'4e182ec4337d6815335fa7ca5cd19e2275b5670a';

@ProviderFor(FinanceNotifier)
final financeProvider = FinanceNotifierProvider._();

final class FinanceNotifierProvider
    extends $NotifierProvider<FinanceNotifier, FinanceState> {
  FinanceNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'financeProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$financeNotifierHash();

  @$internal
  @override
  FinanceNotifier create() => FinanceNotifier();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(FinanceState value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<FinanceState>(value),
    );
  }
}

String _$financeNotifierHash() => r'87e47bd7a5ad756520cf59e61d544ac23c4c79d7';

abstract class _$FinanceNotifier extends $Notifier<FinanceState> {
  FinanceState build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<FinanceState, FinanceState>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<FinanceState, FinanceState>,
              FinanceState,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}
