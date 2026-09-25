import 'package:flutter/material.dart';

extension ToastContext on BuildContext {
  void toast(String message) =>
      ScaffoldMessenger.of(this).showSnackBar(SnackBar(content: Text(message)));
}
