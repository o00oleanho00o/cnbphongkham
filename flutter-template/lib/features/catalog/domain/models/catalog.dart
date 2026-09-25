/// Bundled product catalog and synthetic patient profiles (JSON maps, as in web).
class Catalog {
  Catalog({required this.products, required this.profiles})
    : patientIds = [for (final p in profiles) p['id'] as String],
      _byId = {for (final p in profiles) p['id'] as String: p};

  final List<Map<String, dynamic>> products;
  final List<Map<String, dynamic>> profiles;
  final List<String> patientIds;
  final Map<String, Map<String, dynamic>> _byId;

  Map<String, dynamic> profile(String id) => _byId[id]!;
}
