import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/network/api_config.dart';
import '../../../../core/network/http_client_provider.dart';

part 'finance_remote_data_source.g.dart';

/// HTTP access to `prototype/finance_server.py`.
class FinanceRemoteDataSource {
  const FinanceRemoteDataSource(
    this._client, {
    this.baseUrl = ApiConfig.financeBaseUrl,
  });

  final http.Client _client;
  final String baseUrl;

  Map<String, String> _headers(String role, String doctor) => {
    'Content-Type': 'application/json',
    'X-Pema-Role': role,
    'X-Pema-Doctor': doctor,
  };

  Future<Map<String, dynamic>> fetchState({
    required String month,
    required String role,
    required String doctor,
  }) async {
    final response = await _client
        .get(
          Uri.parse('$baseUrl/state?month=$month'),
          headers: _headers(role, doctor),
        )
        .timeout(const Duration(seconds: 7));
    final value = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode != 200) throw Exception(value['error']);
    return value;
  }

  Future<void> postCommand(
    String action,
    Map<String, dynamic> body, {
    required String role,
    required String doctor,
  }) async {
    final response = await _client
        .post(
          Uri.parse('$baseUrl/command/$action'),
          headers: _headers(role, doctor),
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 8));
    if (response.statusCode != 200) {
      throw Exception((jsonDecode(response.body) as Map)['error']);
    }
  }
}

@Riverpod(keepAlive: true)
FinanceRemoteDataSource financeRemoteDataSource(Ref ref) =>
    FinanceRemoteDataSource(ref.watch(httpClientProvider));
