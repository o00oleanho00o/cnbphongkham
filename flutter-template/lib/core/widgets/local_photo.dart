import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Shows a captured photo from local storage, decoded at display size so a
/// full-resolution JPEG never sits in memory for a thumbnail.
class LocalPhoto extends StatelessWidget {
  const LocalPhoto({
    super.key,
    required this.path,
    this.height = 220,
    this.label,
  });

  final String path;
  final double height;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final ratio = MediaQuery.devicePixelRatioOf(context);
    final placeholder = Container(
      height: height,
      color: const Color(0xFFE8F4FB),
      alignment: Alignment.center,
      child: const Icon(Icons.broken_image_outlined, color: AppColors.muted),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(18),
      child: Stack(
        children: [
          if (kIsWeb)
            placeholder
          else
            Image.file(
              File(path),
              height: height,
              width: double.infinity,
              fit: BoxFit.cover,
              cacheHeight: (height * ratio).round(),
              errorBuilder: (_, _, _) => placeholder,
            ),
          if (label != null)
            Positioned(
              left: 8,
              bottom: 8,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.black54,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 3,
                  ),
                  child: Text(
                    label!,
                    style: const TextStyle(color: Colors.white, fontSize: 11),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
