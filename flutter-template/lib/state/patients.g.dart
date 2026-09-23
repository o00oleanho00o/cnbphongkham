// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'patients.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(PatientsNotifier)
final patientsProvider = PatientsNotifierProvider._();

final class PatientsNotifierProvider
    extends $NotifierProvider<PatientsNotifier, Map<String, PatientState>> {
  PatientsNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'patientsProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$patientsNotifierHash();

  @$internal
  @override
  PatientsNotifier create() => PatientsNotifier();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(Map<String, PatientState> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<Map<String, PatientState>>(value),
    );
  }
}

String _$patientsNotifierHash() => r'9f82c01a5e6a629cea6cc234e754b10f038fa160';

abstract class _$PatientsNotifier extends $Notifier<Map<String, PatientState>> {
  Map<String, PatientState> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref =
        this.ref as $Ref<Map<String, PatientState>, Map<String, PatientState>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<Map<String, PatientState>, Map<String, PatientState>>,
              Map<String, PatientState>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}

@ProviderFor(patientState)
final patientStateProvider = PatientStateFamily._();

final class PatientStateProvider
    extends $FunctionalProvider<PatientState, PatientState, PatientState>
    with $Provider<PatientState> {
  PatientStateProvider._({
    required PatientStateFamily super.from,
    required String super.argument,
  }) : super(
         retry: null,
         name: r'patientStateProvider',
         isAutoDispose: true,
         dependencies: null,
         $allTransitiveDependencies: null,
       );

  @override
  String debugGetCreateSourceHash() => _$patientStateHash();

  @override
  String toString() {
    return r'patientStateProvider'
        ''
        '($argument)';
  }

  @$internal
  @override
  $ProviderElement<PatientState> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  PatientState create(Ref ref) {
    final argument = this.argument as String;
    return patientState(ref, argument);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(PatientState value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<PatientState>(value),
    );
  }

  @override
  bool operator ==(Object other) {
    return other is PatientStateProvider && other.argument == argument;
  }

  @override
  int get hashCode {
    return argument.hashCode;
  }
}

String _$patientStateHash() => r'05b6c41e5ffed680d92da6a2ddcba1562377a460';

final class PatientStateFamily extends $Family
    with $FunctionalFamilyOverride<PatientState, String> {
  PatientStateFamily._()
    : super(
        retry: null,
        name: r'patientStateProvider',
        dependencies: null,
        $allTransitiveDependencies: null,
        isAutoDispose: true,
      );

  PatientStateProvider call(String id) =>
      PatientStateProvider._(argument: id, from: this);

  @override
  String toString() => r'patientStateProvider';
}

@ProviderFor(currentPatient)
final currentPatientProvider = CurrentPatientProvider._();

final class CurrentPatientProvider
    extends $FunctionalProvider<PatientState, PatientState, PatientState>
    with $Provider<PatientState> {
  CurrentPatientProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'currentPatientProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$currentPatientHash();

  @$internal
  @override
  $ProviderElement<PatientState> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  PatientState create(Ref ref) {
    return currentPatient(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(PatientState value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<PatientState>(value),
    );
  }
}

String _$currentPatientHash() => r'85553bdeae37661888c96e6bc88998290167a287';
