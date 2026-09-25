// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'finance_remote_data_source.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(financeRemoteDataSource)
final financeRemoteDataSourceProvider = FinanceRemoteDataSourceProvider._();

final class FinanceRemoteDataSourceProvider
    extends
        $FunctionalProvider<
          FinanceRemoteDataSource,
          FinanceRemoteDataSource,
          FinanceRemoteDataSource
        >
    with $Provider<FinanceRemoteDataSource> {
  FinanceRemoteDataSourceProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'financeRemoteDataSourceProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$financeRemoteDataSourceHash();

  @$internal
  @override
  $ProviderElement<FinanceRemoteDataSource> $createElement(
    $ProviderPointer pointer,
  ) => $ProviderElement(pointer);

  @override
  FinanceRemoteDataSource create(Ref ref) {
    return financeRemoteDataSource(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(FinanceRemoteDataSource value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<FinanceRemoteDataSource>(value),
    );
  }
}

String _$financeRemoteDataSourceHash() =>
    r'e66dc9d58bab516e2c5a26b3b17f661c6d115b4e';
