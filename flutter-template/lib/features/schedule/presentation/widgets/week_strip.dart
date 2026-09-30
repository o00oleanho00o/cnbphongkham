import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';

class WeekStrip extends StatelessWidget {
  const WeekStrip({super.key});
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 20),
    child: Row(
      children: List.generate(
        7,
        (i) => Expanded(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 2),
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              color: i == 1 ? AppColors.blue : Colors.white,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              children: [
                Text(
                  ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'][i],
                  style: TextStyle(
                    fontSize: 10,
                    color: i == 1 ? Colors.white : AppColors.muted,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '${21 + i}',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: i == 1 ? Colors.white : AppColors.ink,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}
