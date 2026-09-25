// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'finance_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
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

String _$financeNotifierHash() => r'9f5a785a5590c63519eb082623be54c0c4a85888';

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
