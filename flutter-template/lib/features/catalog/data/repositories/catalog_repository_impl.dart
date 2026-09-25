import '../../domain/models/catalog.dart';
import '../../domain/repositories/catalog_repository.dart';
import '../datasources/catalog_local_data_source.dart';

class CatalogRepositoryImpl implements CatalogRepository {
  const CatalogRepositoryImpl([this._local = const CatalogLocalDataSource()]);

  final CatalogLocalDataSource _local;

  @override
  Future<Catalog> getCatalog() async => Catalog(
    products: await _local.products(),
    profiles: await _local.profiles(),
  );
}
