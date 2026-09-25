import '../../domain/models/patient_profile.dart';
import '../../domain/models/product.dart';

/// Maps the bundled JSON (same shape as the web prototype) to domain models.
/// JSON keys stay in the data layer; the UI only sees typed models.
abstract final class CatalogMapper {
  static Product product(Map<String, dynamic> json) => Product(
    id: json['id'] as String,
    code: json['code'] as String,
    name: json['name'] as String,
    unit: json['unit'] as String,
    sourceType: json['sourceType'] as String,
    price: (json['price'] as num).round(),
    outputType: json['outputType'] as String,
  );

  static PatientProfile profile(Map<String, dynamic> json) => PatientProfile(
    id: json['id'] as String,
    name: json['name'] as String,
    doctor: json['doctor'] as String,
    sessions: json['sessions'] as int,
    totalSessions: json['total'] as int,
    appointment: json['appointment'] as String,
    day: json['day'] as String,
    careGroup: json['group'] as String? ?? '',
    caseLabel: json['case'] as String? ?? '',
    tasks: [
      for (final t in (json['tasks'] as List? ?? const []).cast<Map>())
        CareTask(
          id: t['id'] as String,
          type: t['type'] as String,
          title: t['title'] as String,
          status: t['status'] as String,
        ),
    ],
  );
}
