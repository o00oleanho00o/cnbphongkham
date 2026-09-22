import 'package:flutter/material.dart';
import 'store.dart';

const _blue = Color(0xFF0B4F94),
    _ink = Color(0xFF17324D),
    _muted = Color(0xFF5D7184),
    _line = Color(0xFFE0EAF2);
const _groups = {
  'd1': 'Sau thủ thuật · D+1',
  'd3': 'Ảnh tiến triển · D+3',
  'd7': 'Bác sĩ review · D+7',
  'due': 'Đến hạn tái khám',
  'overdue': 'Quá hạn tái khám',
  'no_show': 'Vắng hẹn',
  'abandoned': 'Tiếp tục liệu trình',
  'dormant90': 'Kết nối lại · 90 ngày',
  'dormant180': 'Kết nối lại · 180 ngày',
  'birthday': 'Sinh nhật trong tuần',
};

/// A compact work queue: statuses are immediately available, care groups in a sheet.
class CareQueue extends StatefulWidget {
  const CareQueue({super.key, required this.store, required this.onOpen});
  final DemoStore store;
  final VoidCallback onOpen;
  @override
  State<CareQueue> createState() => _CareQueueState();
}

class _CareQueueState extends State<CareQueue> {
  String group = 'all', query = '', bucket = 'Chưa liên hệ';
  DemoStore get s => widget.store;
  String status(Map<String, dynamic> p) =>
      s.states[p['id']]?.careStatus ?? 'Chưa liên hệ';
  List<Map<String, dynamic>> get cases =>
      s.profiles.where((p) => p['group'] != '').toList();
  Future<void> filter() async {
    final selected = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * .8,
      ),
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
          children: [
            const Text(
              'Nhóm chăm sóc',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: _ink,
              ),
            ),
            const SizedBox(height: 4),
            const Text(
              'Chọn nhóm để tập trung xử lý',
              style: TextStyle(color: _muted),
            ),
            const SizedBox(height: 16),
            for (final entry in {'all': 'Tất cả nhóm', ..._groups}.entries)
              ListTile(
                contentPadding: const EdgeInsets.symmetric(horizontal: 8),
                title: Text(
                  entry.value,
                  style: TextStyle(
                    fontSize: 14,
                    color: group == entry.key ? _blue : _ink,
                  ),
                ),
                leading: Icon(
                  group == entry.key
                      ? Icons.radio_button_checked
                      : Icons.radio_button_off,
                  color: group == entry.key ? _blue : _muted,
                  size: 21,
                ),
                trailing: Text(
                  '${cases.where((p) => entry.key == 'all' || p['group'] == entry.key).length}',
                  style: const TextStyle(color: _muted),
                ),
                onTap: () => Navigator.pop(ctx, entry.key),
              ),
          ],
        ),
      ),
    );
    if (selected != null && mounted) setState(() => group = selected);
  }

  @override
  Widget build(BuildContext context) {
    final rows = cases
        .where(
          (p) =>
              status(p) == bucket &&
              (group == 'all' || group == p['group']) &&
              '${p['id']} ${p['name']}'.toLowerCase().contains(query),
        )
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'CSKH hôm nay',
          style: TextStyle(
            fontSize: 26,
            height: 1.25,
            fontWeight: FontWeight.w700,
            color: _ink,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          '${s.staffName} · Chủ nhật, 20/09',
          style: const TextStyle(fontSize: 13, color: _muted),
        ),
        const SizedBox(height: 20),
        Row(
          children: [
            for (final entry in {
              'Chưa liên hệ': 'Cần làm',
              'Đã liên hệ': 'Đã liên hệ',
              'Chờ bác sĩ': 'Chờ bác sĩ',
            }.entries)
              Expanded(
                child: Padding(
                  padding: EdgeInsets.only(
                    right: entry.key == 'Chờ bác sĩ' ? 0 : 8,
                  ),
                  child: Material(
                    color: bucket == entry.key ? _blue : Colors.white,
                    borderRadius: BorderRadius.circular(16),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(16),
                      onTap: () => setState(() => bucket = entry.key),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 12,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${cases.where((p) => status(p) == entry.key).length}',
                              style: TextStyle(
                                fontSize: 25,
                                height: 1.1,
                                fontWeight: FontWeight.w700,
                                color: bucket == entry.key
                                    ? Colors.white
                                    : _ink,
                              ),
                            ),
                            const SizedBox(height: 7),
                            Text(
                              entry.value,
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w500,
                                color: bucket == entry.key
                                    ? Colors.white
                                    : _muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: TextField(
                decoration: const InputDecoration(
                  hintText: 'Tìm tên hoặc mã hồ sơ',
                  hintStyle: TextStyle(fontSize: 13),
                  prefixIcon: Icon(Icons.search, size: 21),
                  contentPadding: EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 12,
                  ),
                ),
                onChanged: (v) =>
                    setState(() => query = v.trim().toLowerCase()),
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              width: 48,
              height: 48,
              child: IconButton.filledTonal(
                tooltip: 'Lọc nhóm chăm sóc',
                onPressed: filter,
                style: IconButton.styleFrom(
                  backgroundColor: group == 'all'
                      ? Colors.white
                      : const Color(0xFFE2F1FB),
                  foregroundColor: _blue,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                    side: const BorderSide(color: _line),
                  ),
                ),
                icon: Badge(
                  isLabelVisible: group != 'all',
                  child: const Icon(Icons.tune, size: 22),
                ),
              ),
            ),
          ],
        ),
        if (group != 'all')
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: InputChip(
              label: Text(
                _groups[group]!,
                style: const TextStyle(fontSize: 12),
              ),
              onDeleted: () => setState(() => group = 'all'),
            ),
          ),
        Padding(
          padding: const EdgeInsets.only(top: 20, bottom: 12),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  bucket == 'Chưa liên hệ' ? 'Danh sách cần chăm sóc' : bucket,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: _ink,
                  ),
                ),
              ),
              Text(
                '${rows.length} khách',
                style: const TextStyle(fontSize: 12, color: _muted),
              ),
            ],
          ),
        ),
        if (rows.isEmpty)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(28),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
            ),
            child: const Column(
              children: [
                Icon(Icons.task_alt, color: _blue, size: 28),
                SizedBox(height: 12),
                Text(
                  'Không có khách trong bộ lọc này',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: _muted),
                ),
              ],
            ),
          ),
        for (final p in rows)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Material(
              color: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(18),
                side: const BorderSide(color: _line),
              ),
              child: InkWell(
                borderRadius: BorderRadius.circular(18),
                onTap: () {
                  s.change(() => s.selected = s.profiles.indexOf(p));
                  widget.onOpen();
                },
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      CircleAvatar(
                        radius: 20,
                        backgroundColor: const Color(0xFFEAF3FA),
                        child: Text(
                          (p['name'] as String)
                              .split(' ')
                              .skip(1)
                              .toList()
                              .reversed
                              .take(2)
                              .toList()
                              .reversed
                              .map((v) => v[0])
                              .join(),
                          style: const TextStyle(
                            color: _blue,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              p['name'] as String,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                                color: _ink,
                              ),
                            ),
                            const SizedBox(height: 5),
                            Text(
                              _groups[p['group']]!,
                              style: const TextStyle(
                                fontSize: 12,
                                color: _blue,
                              ),
                            ),
                            const SizedBox(height: 7),
                            Text(
                              '${p['id']} · ${p['doctor']}',
                              style: const TextStyle(
                                fontSize: 11,
                                color: _muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const Padding(
                        padding: EdgeInsets.only(top: 4),
                        child: Icon(
                          Icons.chevron_right,
                          size: 20,
                          color: _muted,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
