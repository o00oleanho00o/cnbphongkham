import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'features/catalog/data/repositories/catalog_repository_impl.dart';
import 'features/catalog/presentation/providers/catalog_provider.dart';
import 'features/finance/presentation/providers/finance_provider.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final catalog = await const CatalogRepositoryImpl().getCatalog();
  runApp(
    ProviderScope(
      overrides: [
        catalogProvider.overrideWithValue(catalog),
        financeEnabledProvider.overrideWithValue(true),
      ],
      child: const PemaApp(),
    ),
  );
}
