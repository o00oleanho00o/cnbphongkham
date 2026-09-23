import 'package:flutter/material.dart';

/// Chuyển đổi icon outline sang icon filled tương ứng cho trạng thái active
IconData getActiveIcon(IconData outline) {
  if (outline == Icons.space_dashboard_outlined) return Icons.space_dashboard;
  if (outline == Icons.calendar_month_outlined) return Icons.calendar_month;
  if (outline == Icons.people_outline) return Icons.people;
  if (outline == Icons.inbox_outlined) return Icons.inbox;
  if (outline == Icons.grid_view_outlined) return Icons.grid_view;
  if (outline == Icons.home_outlined) return Icons.home;
  if (outline == Icons.route_outlined) return Icons.alt_route;
  if (outline == Icons.chat_bubble_outline) return Icons.chat_bubble;
  if (outline == Icons.person_outline) return Icons.person;
  if (outline == Icons.work_outline) return Icons.work;
  if (outline == Icons.dashboard_outlined) return Icons.dashboard;
  if (outline == Icons.receipt_long_outlined) return Icons.receipt_long;
  if (outline == Icons.payments_outlined) return Icons.payments;
  if (outline == Icons.notifications_outlined) return Icons.notifications;
  return outline;
}

/// Widget thanh điều hướng hiện đại chuẩn Pema & UI/UX Pro Max
///
/// Tính năng:
/// 1. Phân tách rõ ràng với body: Viền trên (top border) 1px + đổ bóng đa tầng (layered shadow)
///    hướng lên trên sắc lam Pema (Color(0x0E0B4F94)).
/// 2. Bo góc dock trên mềm mại (Radius 20) và căn giữa trên tablet (maxWidth: 720).
/// 3. Hiệu ứng Micro-Animation:
///    - Icon Active: Chuyển sang biến thể filled, phóng to nảy nhẹ (scale bounce 1.12, Curves.easeOutBack).
///    - Top Accent Bar: Thanh chỉ mục 36x3px lướt êm ái trên viền trên đến đúng vị trí tab active.
///    - Active Capsule: Viên nang bo tròn 16px màu lam phấn dịu nhẹ (Color(0xFFEAF4FC)) viền mỏng (Color(0xFFD0E6F9)).
/// 4. Bảo toàn 100% khả năng tương thích kiểm thử với [NavigationDestination].
class PemaModernBottomNav extends StatelessWidget {
  const PemaModernBottomNav({
    super.key,
    required this.selectedIndex,
    required this.onDestinationSelected,
    required this.destinations,
    this.maxWidth = 720,
  });

  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final List<NavigationDestination> destinations;
  final double maxWidth;

  List<NavigationDestination> _buildEnhancedDestinations() {
    return List.generate(destinations.length, (i) {
      final dest = destinations[i];
      if (dest.selectedIcon != null) {
        return dest;
      }

      Widget activeIconWidget;
      final rawIcon = dest.icon;

      if (rawIcon is Badge) {
        final badgeChild = rawIcon.child;
        if (badgeChild is Icon && badgeChild.icon != null) {
          final filled = getActiveIcon(badgeChild.icon!);
          activeIconWidget = Badge(
            isLabelVisible: rawIcon.isLabelVisible,
            label: rawIcon.label,
            child: AnimatedScale(
              scale: 1.12,
              duration: const Duration(milliseconds: 260),
              curve: Curves.easeOutBack,
              child: Icon(filled, color: const Color(0xFF0B4F94), size: 24),
            ),
          );
        } else {
          activeIconWidget = rawIcon;
        }
      } else if (rawIcon is Icon && rawIcon.icon != null) {
        final filled = getActiveIcon(rawIcon.icon!);
        activeIconWidget = AnimatedScale(
          scale: 1.12,
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutBack,
          child: Icon(filled, color: const Color(0xFF0B4F94), size: 24),
        );
      } else {
        activeIconWidget = rawIcon;
      }

      return NavigationDestination(
        key: dest.key,
        icon: dest.icon,
        selectedIcon: activeIconWidget,
        label: dest.label,
        tooltip: dest.tooltip,
        enabled: dest.enabled,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final enhancedDestinations = _buildEnhancedDestinations();

    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        border: Border(
          top: BorderSide(color: Color(0xFFE2E8F0), width: 1.0),
        ),
        boxShadow: [
          BoxShadow(
            color: Color(0x0E0B4F94),
            blurRadius: 20,
            spreadRadius: 0,
            offset: Offset(0, -6),
          ),
          BoxShadow(
            color: Color(0x05000000),
            blurRadius: 6,
            spreadRadius: 0,
            offset: Offset(0, -1),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        child: Align(
          alignment: Alignment.bottomCenter,
          heightFactor: 1.0,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth),
            child: Stack(
              children: [
                NavigationBarTheme(
                  data: NavigationBarThemeData(
                    height: 66,
                    backgroundColor: Colors.white,
                    surfaceTintColor: Colors.transparent,
                    elevation: 0,
                    indicatorColor: const Color(0xFFEAF4FC),
                    indicatorShape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                      side: const BorderSide(
                        color: Color(0xFFD0E6F9),
                        width: 1.0,
                      ),
                    ),
                    labelTextStyle: WidgetStateProperty.resolveWith((states) {
                      if (states.contains(WidgetState.selected)) {
                        return const TextStyle(
                          color: Color(0xFF0B4F94),
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          fontFamily: 'BeVietnam',
                          letterSpacing: -0.1,
                        );
                      }
                      return const TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 11.5,
                        fontWeight: FontWeight.w500,
                        fontFamily: 'BeVietnam',
                        letterSpacing: -0.1,
                      );
                    }),
                    iconTheme: WidgetStateProperty.resolveWith((states) {
                      if (states.contains(WidgetState.selected)) {
                        return const IconThemeData(
                          color: Color(0xFF0B4F94),
                          size: 24,
                        );
                      }
                      return const IconThemeData(
                        color: Color(0xFF64748B),
                        size: 23,
                      );
                    }),
                  ),
                  child: NavigationBar(
                    selectedIndex: selectedIndex,
                    onDestinationSelected: onDestinationSelected,
                    animationDuration: const Duration(milliseconds: 300),
                    destinations: enhancedDestinations,
                  ),
                ),
                if (destinations.isNotEmpty)
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    height: 3,
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final count = destinations.length;
                        final tabWidth = constraints.maxWidth / count;
                        const pillWidth = 36.0;
                        final left = (selectedIndex * tabWidth) +
                            (tabWidth - pillWidth) / 2;
                        return Stack(
                          children: [
                            AnimatedPositioned(
                              duration: const Duration(milliseconds: 300),
                              curve: Curves.easeOutCubic,
                              left: left.clamp(0.0, constraints.maxWidth - pillWidth),
                              child: Container(
                                width: pillWidth,
                                height: 3,
                                decoration: BoxDecoration(
                                  color: const Color(0xFF0B4F94),
                                  borderRadius: BorderRadius.circular(2),
                                  boxShadow: const [
                                    BoxShadow(
                                      color: Color(0x550B4F94),
                                      blurRadius: 4,
                                      offset: Offset(0, 1),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
