import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'catalog.g.dart';

class Catalog {
  Catalog({required this.products, required this.profiles})
    : patientIds = [for (final p in profiles) p['id'] as String],
      _byId = {for (final p in profiles) p['id'] as String: p};

  final List<Map<String, dynamic>> products;
  final List<Map<String, dynamic>> profiles;
  final List<String> patientIds;
  final Map<String, Map<String, dynamic>> _byId;

  Map<String, dynamic> profile(String id) => _byId[id]!;

  static Future<Catalog> load() async {
    Future<List<Map<String, dynamic>>> read(String path) async =>
        (jsonDecode(await rootBundle.loadString(path)) as List)
            .cast<Map<String, dynamic>>();
    return Catalog(
      products: await read('assets/products.json'),
      profiles: await read('assets/patients.json'),
    );
  }
}

/// Loaded before `runApp` and injected with `overrideWithValue`.
@Riverpod(keepAlive: true)
Catalog catalog(Ref ref) =>
    throw UnimplementedError('Override catalogProvider with Catalog.load()');
