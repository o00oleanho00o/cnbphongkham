import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'main.dart';

class OnboardingFlow extends StatefulWidget {
  final VoidCallback onComplete;
  const OnboardingFlow({super.key, required this.onComplete});

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends State<OnboardingFlow> {
  final _pageController = PageController();
  int _page = 0;

  void _goTo(int index) {
    _pageController.animateToPage(
      index,
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: PageView(
        controller: _pageController,
        physics: const NeverScrollableScrollPhysics(),
        onPageChanged: (i) => setState(() => _page = i),
        children: [
          _WelcomePage(
            onSignIn: () => _goTo(2),
            onNext: () => _goTo(1),
            dots: _Dots(count: 3, index: _page, light: true),
          ),
          _ValuePage(
            onSkip: () => _goTo(2),
            onNext: () => _goTo(2),
            dots: _Dots(count: 3, index: _page, light: false),
          ),
          _SignInPage(
            onBack: () => _goTo(1),
            onComplete: widget.onComplete,
            dots: _Dots(count: 3, index: _page, light: false),
          ),
        ],
      ),
    );
  }
}

class _Dots extends StatelessWidget {
  final int count;
  final int index;
  final bool light;
  const _Dots({required this.count, required this.index, required this.light});

  @override
  Widget build(BuildContext context) {
    final base = light ? Colors.white.withValues(alpha: .42) : const Color(0xFFCBD8E2);
    final active = light ? Colors.white : blue;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(count, (i) {
        final on = i == index;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
          margin: const EdgeInsets.symmetric(horizontal: 3),
          width: on ? 22 : 7,
          height: 7,
          decoration: BoxDecoration(
            color: on ? active : base,
            borderRadius: BorderRadius.circular(99),
          ),
        );
      }),
    );
  }
}

class _BrandMark extends StatelessWidget {
  final Color color;
  const _BrandMark({required this.color});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.favorite_outline, color: color, size: 20),
        const SizedBox(width: 8),
        Text(
          'Pema Care',
          style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 16),
        ),
      ],
    );
  }
}

class _WelcomePage extends StatelessWidget {
  final VoidCallback onSignIn;
  final VoidCallback onNext;
  final Widget dots;
  const _WelcomePage({required this.onSignIn, required this.onNext, required this.dots});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [navy, blue],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            right: -30,
            top: 56,
            child: Icon(Icons.spa_outlined, size: 220, color: Colors.white.withValues(alpha: .08)),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(28, 8, 20, 28),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const _BrandMark(color: Colors.white),
                      TextButton(
                        onPressed: onSignIn,
                        style: TextButton.styleFrom(foregroundColor: Colors.white.withValues(alpha: .92)),
                        child: const Text('Bỏ qua'),
                      ),
                    ],
                  ),
                  const Spacer(),
                  const Text(
                    'Chăm sóc da,\nđồng hành mỗi ngày.',
                    style: TextStyle(color: Colors.white, fontSize: 32, height: 1.15, fontWeight: FontWeight.w700, letterSpacing: -.5),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    'Theo dõi lịch hẹn, đơn thuốc và hướng dẫn sau điều trị — cùng đội ngũ Pema, ngay trên điện thoại của bạn.',
                    style: TextStyle(color: Colors.white.withValues(alpha: .86), fontSize: 15, height: 1.5),
                  ),
                  const Spacer(flex: 2),
                  dots,
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: onNext,
                    style: FilledButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: navy,
                      minimumSize: const Size(48, 54),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
                      textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                    ),
                    child: const Text('Bắt đầu'),
                  ),
                  const SizedBox(height: 14),
                  Center(
                    child: RichText(
                      text: TextSpan(
                        style: TextStyle(color: Colors.white.withValues(alpha: .78), fontSize: 13.5),
                        children: [
                          const TextSpan(text: 'Đã có tài khoản? '),
                          TextSpan(
                            text: 'Đăng nhập',
                            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, decoration: TextDecoration.underline),
                            recognizer: TapGestureRecognizer()..onTap = onSignIn,
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ValuePage extends StatelessWidget {
  final VoidCallback onSkip;
  final VoidCallback onNext;
  final Widget dots;
  const _ValuePage({required this.onSkip, required this.onNext, required this.dots});

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: paper,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(28, 8, 24, 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const _BrandMark(color: navy),
                  TextButton(onPressed: onSkip, child: const Text('Bỏ qua')),
                ],
              ),
              const SizedBox(height: 4),
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(height: 8),
                      const Text(
                        'Mọi bước chăm sóc,\nrõ ràng từng buổi.',
                        style: TextStyle(fontSize: 26, height: 1.18, fontWeight: FontWeight.w700, color: navy, letterSpacing: -.4),
                      ),
                      const SizedBox(height: 10),
                      const Text(
                        'Pema Care giúp bạn nắm được hành trình điều trị mà không cần hỏi lại đội ngũ phòng khám.',
                        style: TextStyle(fontSize: 14.5, height: 1.5, color: muted),
                      ),
                      const SizedBox(height: 24),
                      const _ValueRow(
                        icon: Icons.calendar_month_outlined,
                        title: 'Lịch hẹn & nhắc nhở',
                        body: 'Xem giờ khám, bác sĩ phụ trách và đổi lịch chỉ trong vài chạm.',
                      ),
                      const SizedBox(height: 16),
                      const _ValueRow(
                        icon: Icons.medication_outlined,
                        title: 'Đơn thuốc rõ ràng',
                        body: 'Toa thuốc và phiếu tư vấn đã được bác sĩ duyệt, xem lại bất cứ lúc nào.',
                      ),
                      const SizedBox(height: 16),
                      const _ValueRow(
                        icon: Icons.favorite_outline,
                        title: 'Hướng dẫn chăm sóc tại nhà',
                        body: 'Nhận hướng dẫn sau điều trị và gửi cập nhật ảnh cho đội ngũ Pema.',
                      ),
                    ],
                  ),
                ),
              ),
              dots,
              const SizedBox(height: 20),
              FilledButton(
                onPressed: onNext,
                style: FilledButton.styleFrom(
                  minimumSize: const Size(48, 54),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
                ),
                child: const Text('Tiếp tục'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ValueRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String body;
  const _ValueRow({required this.icon, required this.title, required this.body});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: const Color(0xFFE8F4FB),
            borderRadius: BorderRadius.circular(11),
            border: Border.all(color: const Color(0xFFCFE6F5)),
          ),
          child: Icon(icon, size: 18, color: blue),
        ),
        const SizedBox(width: 13),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: ink)),
              const SizedBox(height: 3),
              Text(body, style: const TextStyle(fontSize: 12.5, color: muted, height: 1.4)),
            ],
          ),
        ),
      ],
    );
  }
}

enum _SignInStatus { idle, sending, sent }

class _SignInPage extends StatefulWidget {
  final VoidCallback onBack;
  final VoidCallback onComplete;
  final Widget dots;
  const _SignInPage({required this.onBack, required this.onComplete, required this.dots});

  @override
  State<_SignInPage> createState() => _SignInPageState();
}

class _SignInPageState extends State<_SignInPage> {
  final _phoneController = TextEditingController();
  final _focusNode = FocusNode();
  String? _error;
  bool _touched = false;
  _SignInStatus _status = _SignInStatus.idle;
  int _resendCooldown = 0;
  Timer? _resendTimer;

  @override
  void initState() {
    super.initState();
    _focusNode.addListener(() {
      if (!_focusNode.hasFocus && _phoneController.text.trim().isNotEmpty) {
        setState(() {
          _touched = true;
          _error = _diagnose(_phoneController.text);
        });
      }
    });
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _focusNode.dispose();
    _resendTimer?.cancel();
    super.dispose();
  }

  String? _diagnose(String raw) {
    final v = raw.replaceAll(RegExp(r'[\s.-]'), '');
    if (v.isEmpty) return 'Nhập số điện thoại để nhận mã xác nhận.';
    final ok = RegExp(r'^(0|\+84)(3|5|7|8|9)\d{8}$').hasMatch(v);
    if (!ok) return 'Số điện thoại chưa đúng định dạng Việt Nam, ví dụ 0901 234 567.';
    return null;
  }

  Future<void> _submit() async {
    final err = _diagnose(_phoneController.text);
    setState(() {
      _touched = true;
      _error = err;
    });
    if (err != null) return;
    setState(() => _status = _SignInStatus.sending);
    await Future.delayed(const Duration(milliseconds: 900));
    if (!mounted) return;
    setState(() => _status = _SignInStatus.sent);
    _startResendCooldown();
  }

  void _startResendCooldown() {
    _resendTimer?.cancel();
    setState(() => _resendCooldown = 30);
    _resendTimer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) {
        t.cancel();
        return;
      }
      if (_resendCooldown <= 1) {
        t.cancel();
        setState(() => _resendCooldown = 0);
      } else {
        setState(() => _resendCooldown -= 1);
      }
    });
  }

  void _changeNumber() {
    _resendTimer?.cancel();
    setState(() {
      _status = _SignInStatus.idle;
      _touched = false;
      _error = null;
      _resendCooldown = 0;
      _phoneController.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: paper,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 24, 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  IconButton(
                    onPressed: _status == _SignInStatus.sending ? null : widget.onBack,
                    icon: const Icon(Icons.arrow_back, color: navy),
                    tooltip: 'Quay lại',
                  ),
                  const SizedBox(width: 2),
                  const _BrandMark(color: navy),
                ],
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: _status == _SignInStatus.sent ? _buildSent() : _buildForm(),
                ),
              ),
              widget.dots,
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildForm() {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Lưu lại hồ sơ của bạn.',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: navy, letterSpacing: -.3),
          ),
          const SizedBox(height: 8),
          const Text(
            'Nhập số điện thoại để đồng bộ lịch hẹn, đơn thuốc và hướng dẫn chăm sóc trên mọi thiết bị.',
            style: TextStyle(fontSize: 14, color: muted, height: 1.5),
          ),
          const SizedBox(height: 22),
          const Text('Số điện thoại', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: ink)),
          const SizedBox(height: 7),
          TextField(
            controller: _phoneController,
            focusNode: _focusNode,
            keyboardType: TextInputType.phone,
            autofillHints: const [AutofillHints.telephoneNumber],
            enabled: _status != _SignInStatus.sending,
            onChanged: (v) {
              if (_touched) setState(() => _error = _diagnose(v));
            },
            onSubmitted: (_) => _submit(),
            decoration: InputDecoration(
              hintText: '0901 234 567',
              errorText: _touched ? _error : null,
              errorMaxLines: 2,
            ),
          ),
          const SizedBox(height: 8),
          if (!_touched || _error == null)
            const Text(
              'Chúng tôi gửi mã xác nhận qua SMS. Không cần mật khẩu.',
              style: TextStyle(fontSize: 12.5, color: muted),
            ),
          const SizedBox(height: 22),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _status == _SignInStatus.sending ? null : _submit,
              style: FilledButton.styleFrom(
                minimumSize: const Size(48, 54),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
              ),
              child: _status == _SignInStatus.sending
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white),
                    )
                  : const Text('Tiếp tục bằng số điện thoại'),
            ),
          ),
          const SizedBox(height: 22),
          const Row(
            children: [
              Expanded(child: Divider(color: Color(0xFFE1E9EF))),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: 12),
                child: Text('hoặc', style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600, color: muted, letterSpacing: 1)),
              ),
              Expanded(child: Divider(color: Color(0xFFE1E9EF))),
            ],
          ),
          const SizedBox(height: 18),
          _OAuthButton(label: 'Tiếp tục với Google', onTap: widget.onComplete),
          const SizedBox(height: 10),
          _OAuthButton(label: 'Tiếp tục với Apple', onTap: widget.onComplete),
          const SizedBox(height: 18),
          const Text.rich(
            TextSpan(
              style: TextStyle(fontSize: 11.5, color: muted, height: 1.5),
              children: [
                TextSpan(text: 'Bằng việc tiếp tục, bạn đồng ý với '),
                TextSpan(text: 'Điều khoản dịch vụ', style: TextStyle(decoration: TextDecoration.underline)),
                TextSpan(text: ' và '),
                TextSpan(text: 'Chính sách bảo mật', style: TextStyle(decoration: TextDecoration.underline)),
                TextSpan(text: ' của Pema.'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSent() {
    final phone = _phoneController.text.trim();
    return Padding(
      padding: const EdgeInsets.only(top: 24),
      child: Column(
        children: [
          Container(
            width: 62,
            height: 62,
            decoration: BoxDecoration(
              color: const Color(0xFFE8F4FB),
              shape: BoxShape.circle,
              border: Border.all(color: const Color(0xFFCFE6F5)),
            ),
            child: const Icon(Icons.mark_email_read_outlined, color: blue, size: 28),
          ),
          const SizedBox(height: 16),
          const Text('Kiểm tra tin nhắn', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: navy)),
          const SizedBox(height: 8),
          RichText(
            textAlign: TextAlign.center,
            text: TextSpan(
              style: const TextStyle(fontSize: 13.5, color: muted, height: 1.5),
              children: [
                const TextSpan(text: 'Mã xác nhận đã được gửi tới '),
                TextSpan(text: phone, style: const TextStyle(color: ink, fontWeight: FontWeight.w600)),
                const TextSpan(text: '. Mã có hiệu lực trong 5 phút.'),
              ],
            ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: widget.onComplete,
              style: FilledButton.styleFrom(
                minimumSize: const Size(48, 54),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
              ),
              child: const Text('Vào ứng dụng'),
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              onPressed: _resendCooldown > 0 ? null : _submit,
              style: OutlinedButton.styleFrom(
                minimumSize: const Size(48, 52),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
              ),
              child: Text(_resendCooldown > 0 ? 'Gửi lại mã sau ${_resendCooldown}s' : 'Gửi lại mã'),
            ),
          ),
          const SizedBox(height: 8),
          TextButton(onPressed: _changeNumber, child: const Text('Dùng số khác')),
        ],
      ),
    );
  }
}

class _OAuthButton extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _OAuthButton({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton(
        onPressed: onTap,
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 52),
          side: const BorderSide(color: Color(0xFFD9E5EE)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
          foregroundColor: ink,
        ),
        child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
      ),
    );
  }
}
