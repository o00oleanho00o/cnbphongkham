import '../../domain/models/catalog.dart';
import '../../domain/repositories/catalog_repository.dart';
import '../datasources/catalog_local_data_source.dart';
import '../mappers/catalog_mapper.dart';

class CatalogRepositoryImpl implements CatalogRepository {
  const CatalogRepositoryImpl([this._local = const CatalogLocalDataSource()]);

  final CatalogLocalDataSource _local;

  @override
  Future<Catalog> getCatalog() async => Catalog(
    products: [
      for (final p in await _local.products()) CatalogMapper.product(p),
    ],
    profiles: [
      for (final p in await _local.profiles()) CatalogMapper.profile(p),
    ],
  );
}
