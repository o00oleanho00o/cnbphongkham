import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'main.dart';

class PemaBottomNav extends StatelessWidget {
  final List<String> labels;
  final List<IconData> icons;
  final List<IconData> selectedIcons;
  final int index;
  final ValueChanged<int> onChanged;
  const PemaBottomNav({
    super.key,
    required this.labels,
    required this.icons,
    required this.selectedIcons,
    required this.index,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: .07), blurRadius: 18, offset: const Offset(0, -6)),
        ],
        border: const Border(top: BorderSide(color: Color(0xFFEAF1F6))),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 64,
          child: Row(
            children: List.generate(labels.length, (i) {
              final selected = i == index;
              return Expanded(
                child: _NavItem(
                  icon: selected ? selectedIcons[i] : icons[i],
                  label: labels[i],
                  selected: selected,
                  onTap: () {
                    if (!selected) {
                      HapticFeedback.selectionClick();
                      onChanged(i);
                    }
                  },
                ),
              );
            }),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _NavItem({required this.icon, required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final color = selected ? blue : muted;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: InkWell(
        onTap: onTap,
        splashColor: blue.withValues(alpha: .08),
        highlightColor: blue.withValues(alpha: .05),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                curve: Curves.easeOut,
                padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 5),
                decoration: BoxDecoration(
                  color: selected ? const Color(0xFFE0F0FA) : Colors.transparent,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: AnimatedScale(
                  scale: selected ? 1.08 : 1.0,
                  duration: const Duration(milliseconds: 200),
                  curve: Curves.easeOut,
                  child: Icon(icon, size: 22, color: color),
                ),
              ),
              const SizedBox(height: 4),
              AnimatedDefaultTextStyle(
                duration: const Duration(milliseconds: 200),
                style: TextStyle(
                  fontFamily: 'BeVietnam',
                  fontSize: 11,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  color: color,
                  letterSpacing: -.1,
                ),
                child: Text(label),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
