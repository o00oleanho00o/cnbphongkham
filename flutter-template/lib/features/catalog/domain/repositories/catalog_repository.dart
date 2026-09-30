import '../models/catalog.dart';

abstract interface class CatalogRepository {
  Future<Catalog> getCatalog();
}
