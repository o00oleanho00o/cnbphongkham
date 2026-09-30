import 'dart:convert';

import 'package:flutter/services.dart';

/// Reads the catalog JSON bundled under `assets/`.
class CatalogLocalDataSource {
  const CatalogLocalDataSource();

  Future<List<Map<String, dynamic>>> products() =>
      _read('assets/products.json');

  Future<List<Map<String, dynamic>>> profiles() =>
      _read('assets/patients.json');

  Future<List<Map<String, dynamic>>> _read(String path) async =>
      (jsonDecode(await rootBundle.loadString(path)) as List)
          .cast<Map<String, dynamic>>();
}
