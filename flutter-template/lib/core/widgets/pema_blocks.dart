import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

Widget heading(String title, String sub) => Padding(
  padding: const EdgeInsets.only(bottom: 20),
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        title,
        style: const TextStyle(
          fontSize: 25,
          fontWeight: FontWeight.w700,
          color: AppColors.navy,
        ),
      ),
      const SizedBox(height: 6),
      Text(sub, style: const TextStyle(color: AppColors.muted, fontSize: 13)),
    ],
  ),
);
Widget section(String title) => Padding(
  padding: const EdgeInsets.only(top: 24, bottom: 12),
  child: Text(
    title,
    style: const TextStyle(
      fontSize: 17,
      fontWeight: FontWeight.w700,
      color: AppColors.ink,
    ),
  ),
);
Widget hero(String title, String sub, IconData icon) => Container(
  clipBehavior: Clip.antiAlias,
  decoration: BoxDecoration(
    borderRadius: BorderRadius.circular(24),
    gradient: const LinearGradient(
      colors: [AppColors.navy, AppColors.blue],
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
    ),
  ),
  child: Stack(
    children: [
      Positioned(
        right: -20,
        top: -22,
        child: Icon(
          icon,
          size: 170,
          color: Colors.white.withValues(alpha: .09),
        ),
      ),
      Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'PEMA • CHĂM SÓC LIÊN TỤC',
              style: TextStyle(
                color: Color(0xFFB8DEF5),
                fontSize: 10,
                letterSpacing: 1.4,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 24,
                height: 1.3,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              sub,
              style: const TextStyle(color: Color(0xFFD7E9F5), fontSize: 12),
            ),
          ],
        ),
      ),
    ],
  ),
);
Widget metric(String value, String label) => Expanded(
  child: Container(
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: const TextStyle(
            fontSize: 28,
            color: AppColors.blue,
            fontWeight: FontWeight.w700,
          ),
        ),
        Text(
          label,
          style: const TextStyle(color: AppColors.muted, fontSize: 12),
        ),
      ],
    ),
  ),
);
Widget tile(String title, String sub, IconData icon, VoidCallback? tap) => Card(
  elevation: 0,
  margin: const EdgeInsets.only(bottom: 10),
  color: Colors.white,
  shape: RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(18),
    side: const BorderSide(color: Color(0xFFE3ECF3)),
  ),
  child: ListTile(
    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
    leading: CircleAvatar(
      backgroundColor: const Color(0xFFE8F4FB),
      child: Icon(icon, color: AppColors.blue, size: 21),
    ),
    title: Text(
      title,
      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
    ),
    subtitle: Text(
      sub,
      style: const TextStyle(fontSize: 12, color: AppColors.muted),
    ),
    trailing: tap == null
        ? null
        : const Icon(Icons.chevron_right, size: 18, color: AppColors.muted),
    onTap: tap,
  ),
);
Widget notice(String text) => Container(
  margin: const EdgeInsets.only(bottom: 16),
  padding: const EdgeInsets.all(16),
  decoration: BoxDecoration(
    color: const Color(0xFFE8F4FB),
    borderRadius: BorderRadius.circular(14),
  ),
  child: Text(
    text,
    style: const TextStyle(fontSize: 12, color: AppColors.navy),
  ),
);
Widget primary(String text, VoidCallback? tap) => Padding(
  padding: const EdgeInsets.symmetric(vertical: 8),
  child: FilledButton(onPressed: tap, child: Text(text)),
);
