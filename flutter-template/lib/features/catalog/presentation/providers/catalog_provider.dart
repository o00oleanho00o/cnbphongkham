import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/models/catalog.dart';

part 'catalog_provider.g.dart';

/// Loaded before `runApp` via `CatalogRepository` and injected with
/// `overrideWithValue`, so screens read it synchronously.
@Riverpod(keepAlive: true)
Catalog catalog(Ref ref) => throw UnimplementedError(
  'Override catalogProvider with CatalogRepository.getCatalog()',
);
