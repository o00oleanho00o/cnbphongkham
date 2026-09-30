// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'session_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(SessionNotifier)
final sessionProvider = SessionNotifierProvider._();

final class SessionNotifierProvider
    extends $NotifierProvider<SessionNotifier, Session> {
  SessionNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'sessionProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$sessionNotifierHash();

  @$internal
  @override
  SessionNotifier create() => SessionNotifier();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(Session value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<Session>(value),
    );
  }
}

String _$sessionNotifierHash() => r'5cda87c001c77441a7a1fe7d519464b5882ead5c';

abstract class _$SessionNotifier extends $Notifier<Session> {
  Session build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<Session, Session>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<Session, Session>,
              Session,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}

@ProviderFor(selectedProfile)
final selectedProfileProvider = SelectedProfileProvider._();

final class SelectedProfileProvider
    extends $FunctionalProvider<PatientProfile, PatientProfile, PatientProfile>
    with $Provider<PatientProfile> {
  SelectedProfileProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'selectedProfileProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$selectedProfileHash();

  @$internal
  @override
  $ProviderElement<PatientProfile> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  PatientProfile create(Ref ref) {
    return selectedProfile(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(PatientProfile value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<PatientProfile>(value),
    );
  }
}

String _$selectedProfileHash() => r'dae3bc0a82020b462399880d6304093b8e3d15e9';

@ProviderFor(selectedPatientId)
final selectedPatientIdProvider = SelectedPatientIdProvider._();

final class SelectedPatientIdProvider
    extends $FunctionalProvider<String, String, String>
    with $Provider<String> {
  SelectedPatientIdProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'selectedPatientIdProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$selectedPatientIdHash();

  @$internal
  @override
  $ProviderElement<String> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  String create(Ref ref) {
    return selectedPatientId(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(String value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<String>(value),
    );
  }
}

String _$selectedPatientIdHash() => r'bef9d8e49cb8140e44dbaf6d322ea61fe89d38e3';
