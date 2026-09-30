// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'care_queue_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// Profiles in the CSKH queue with their contact status. Cart edits produce an
/// equal list, so `updateShouldNotify` keeps the queue from rebuilding.

@ProviderFor(CareCases)
final careCasesProvider = CareCasesProvider._();

/// Profiles in the CSKH queue with their contact status. Cart edits produce an
/// equal list, so `updateShouldNotify` keeps the queue from rebuilding.
final class CareCasesProvider
    extends $NotifierProvider<CareCases, List<CareCase>> {
  /// Profiles in the CSKH queue with their contact status. Cart edits produce an
  /// equal list, so `updateShouldNotify` keeps the queue from rebuilding.
  CareCasesProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'careCasesProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$careCasesHash();

  @$internal
  @override
  CareCases create() => CareCases();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<CareCase> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<CareCase>>(value),
    );
  }
}

String _$careCasesHash() => r'd28e0cf60a72da44b031058f8c5cc17280148d1a';

/// Profiles in the CSKH queue with their contact status. Cart edits produce an
/// equal list, so `updateShouldNotify` keeps the queue from rebuilding.

abstract class _$CareCases extends $Notifier<List<CareCase>> {
  List<CareCase> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<List<CareCase>, List<CareCase>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<List<CareCase>, List<CareCase>>,
              List<CareCase>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}
