// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'catalog_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// Loaded before `runApp` via `CatalogRepository` and injected with
/// `overrideWithValue`, so screens read it synchronously.

@ProviderFor(catalog)
final catalogProvider = CatalogProvider._();

/// Loaded before `runApp` via `CatalogRepository` and injected with
/// `overrideWithValue`, so screens read it synchronously.

final class CatalogProvider
    extends $FunctionalProvider<Catalog, Catalog, Catalog>
    with $Provider<Catalog> {
  /// Loaded before `runApp` via `CatalogRepository` and injected with
  /// `overrideWithValue`, so screens read it synchronously.
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

String _$catalogHash() => r'bcdcd287d87ea20aa1afd95e823e80ba1cb6a773';
