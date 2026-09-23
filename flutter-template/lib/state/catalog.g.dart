// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'catalog.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// Loaded before `runApp` and injected with `overrideWithValue`.

@ProviderFor(catalog)
final catalogProvider = CatalogProvider._();

/// Loaded before `runApp` and injected with `overrideWithValue`.

final class CatalogProvider
    extends $FunctionalProvider<Catalog, Catalog, Catalog>
    with $Provider<Catalog> {
  /// Loaded before `runApp` and injected with `overrideWithValue`.
  CatalogProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'catalogProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$catalogHash();

  @$internal
  @override
  $ProviderElement<Catalog> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  Catalog create(Ref ref) {
    return catalog(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(Catalog value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<Catalog>(value),
    );
  }
}

String _$catalogHash() => r'877f0a1dc6d85b901cc15af91f9019235b6a1d7b';
