// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'review_queue_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// Owned profiles that need a doctor's review: a D+7 task, a patient update
/// or a CSKH escalation. Unrelated edits produce an equal list, so
/// `updateShouldNotify` keeps the workspace from rebuilding.

@ProviderFor(ReviewQueue)
final reviewQueueProvider = ReviewQueueProvider._();

/// Owned profiles that need a doctor's review: a D+7 task, a patient update
/// or a CSKH escalation. Unrelated edits produce an equal list, so
/// `updateShouldNotify` keeps the workspace from rebuilding.
final class ReviewQueueProvider
    extends $NotifierProvider<ReviewQueue, List<PatientProfile>> {
  /// Owned profiles that need a doctor's review: a D+7 task, a patient update
  /// or a CSKH escalation. Unrelated edits produce an equal list, so
  /// `updateShouldNotify` keeps the workspace from rebuilding.
  ReviewQueueProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'reviewQueueProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$reviewQueueHash();

  @$internal
  @override
  ReviewQueue create() => ReviewQueue();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<PatientProfile> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<PatientProfile>>(value),
    );
  }
}

String _$reviewQueueHash() => r'f04b1f311cb976f06a2d975f7b9bf403ae10f23f';

/// Owned profiles that need a doctor's review: a D+7 task, a patient update
/// or a CSKH escalation. Unrelated edits produce an equal list, so
/// `updateShouldNotify` keeps the workspace from rebuilding.

abstract class _$ReviewQueue extends $Notifier<List<PatientProfile>> {
  List<PatientProfile> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<List<PatientProfile>, List<PatientProfile>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<List<PatientProfile>, List<PatientProfile>>,
              List<PatientProfile>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}
