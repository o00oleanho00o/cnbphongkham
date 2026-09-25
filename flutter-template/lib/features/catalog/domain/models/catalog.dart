import 'patient_profile.dart';
import 'product.dart';

/// Bundled product catalog and synthetic patient profiles. Loaded once.
class Catalog {
  Catalog({required this.products, required this.profiles})
    : patientIds = [for (final p in profiles) p.id],
      _indexById = {
        for (var i = 0; i < profiles.length; i++) profiles[i].id: i,
      };

  final List<Product> products;
  final List<PatientProfile> profiles;
  final List<String> patientIds;
  final Map<String, int> _indexById;

  PatientProfile profile(String id) => profiles[_indexById[id]!];

  /// Position used by the session's patient selection.
  int indexOf(String id) => _indexById[id]!;
}
