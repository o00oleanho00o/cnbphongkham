import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:pema_native_template/features/catalog/data/repositories/catalog_repository_impl.dart';
import 'package:pema_native_template/features/catalog/domain/models/catalog.dart';
import 'package:pema_native_template/features/catalog/presentation/providers/catalog_provider.dart';

Future<Catalog> loadCatalog() => const CatalogRepositoryImpl().getCatalog();

ProviderContainer clinicContainer(Catalog catalog) => ProviderContainer.test(
  overrides: [catalogProvider.overrideWithValue(catalog)],
);

Widget scoped(ProviderContainer container, Widget child) =>
    UncontrolledProviderScope(container: container, child: child);
