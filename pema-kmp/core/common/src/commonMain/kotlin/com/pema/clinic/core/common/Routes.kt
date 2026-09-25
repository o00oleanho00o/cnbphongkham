package com.pema.clinic.core.common

/**
 * Navigation route ids (ASCII, safe for Compose Navigation) plus the Vietnamese
 * titles that the Flutter app used as route names. [titleOf] maps an id to the
 * title shown in app bars and used for `Session.allows`.
 */
object Routes {
    const val Workspace = "workspace"
    const val SessionPicker = "session-picker"
    const val Finance = "finance"
    const val FinanceProcedure = "finance/procedure"
    const val FinanceRates = "finance/rates"

    const val CustomerCare = "customer-care"
    const val Patient360 = "patient-360"
    const val Consultation = "consultation"
    const val TreatmentPlan = "treatment-plan"
    const val TreatmentSession = "treatment-session"
    const val ProgressPhotos = "progress-photos"
    const val AskPema = "ask-pema"
    const val QuickOrder = "quick-order"
    const val OrderReview = "order-review"
    const val Prescriptions = "prescriptions"
    const val A5Print = "a5-print"
    const val Invoices = "invoices"
    const val Cashier = "cashier"
    const val Booking = "booking"
    const val AppointmentDetail = "appointment-detail"
    const val MyAppointments = "my-appointments"
    const val Services = "services"
    const val Resources = "resources"
    const val HomeCare = "home-care"
    const val SendUpdate = "send-update"
    const val FollowUpReply = "follow-up-reply"
    const val Privacy = "privacy"
    const val Guide = "guide"

    val titles: Map<String, String> = mapOf(
        Workspace to "Không gian làm việc",
        SessionPicker to "Chọn không gian",
        Finance to "/finance",
        FinanceProcedure to "Thủ thuật",
        FinanceRates to "Tỷ lệ chia",
        CustomerCare to "Chăm sóc khách hàng",
        Patient360 to "Patient 360",
        Consultation to "Tư vấn",
        TreatmentPlan to "Kế hoạch điều trị",
        TreatmentSession to "Buổi điều trị",
        ProgressPhotos to "Ảnh tiến triển",
        AskPema to "Ask Pema",
        QuickOrder to "Lên đơn nhanh",
        OrderReview to "Kiểm tra đơn",
        Prescriptions to "Đơn thuốc & tư vấn",
        A5Print to "Phiếu A5",
        Invoices to "Hóa đơn",
        Cashier to "Thu ngân",
        Booking to "Đặt lịch",
        AppointmentDetail to "Chi tiết lịch",
        MyAppointments to "Lịch của tôi",
        Services to "Dịch vụ",
        Resources to "Bác sĩ & phòng",
        HomeCare to "Chăm sóc tại nhà",
        SendUpdate to "Gửi cập nhật",
        FollowUpReply to "Phản hồi",
        Privacy to "Quyền riêng tư",
        Guide to "Hướng dẫn",
    )

    /** Title (= Flutter route name) for a route id; unknown ids are returned unchanged. */
    fun titleOf(route: String): String = titles[route] ?: route

    /** Route id for a Flutter route name / title (used when porting data that stores titles). */
    fun idOf(title: String): String? = titles.entries.firstOrNull { it.value == title }?.key

    val flutterRoutes = listOf(
        Finance, CustomerCare, Patient360, Consultation, TreatmentPlan, TreatmentSession,
        ProgressPhotos, AskPema, QuickOrder, OrderReview, Prescriptions, A5Print, Invoices,
        Cashier, Booking, AppointmentDetail, MyAppointments, Services, Resources, HomeCare,
        SendUpdate, FollowUpReply, Privacy, Guide,
    )

    val all = listOf(Workspace, SessionPicker, FinanceProcedure, FinanceRates) + flutterRoutes

    /** NavHost pattern for Finance; `tab` is the Flutter `initialTab` argument (0..3). */
    const val FinancePattern = "finance?tab={tab}"
    fun finance(tab: Int = 0): String = "finance?tab=$tab"

    /** NavHost pattern for Flutter `GuideScreen(route:)` – also the fallback for unknown routes. */
    const val GuidePattern = "guide?route={route}"
    fun guide(title: String = titleOf(Guide)): String = "guide?route=" + encodeArg(title)

    /** NavHost pattern for Flutter `_RouteGuard`'s "not in this workspace" screen. */
    const val DeniedPattern = "denied?route={route}"
    fun denied(title: String): String = "denied?route=" + encodeArg(title)

    /** Percent-encodes a query argument (UTF-8), e.g. "Đơn thuốc & tư vấn". */
    fun encodeArg(value: String): String = buildString {
        for (b in value.encodeToByteArray()) {
            val c = b.toInt() and 0xFF
            if (c < 0x80 && (c.toChar().isLetterOrDigit() || c.toChar() in "-_.~")) append(c.toChar())
            else append('%').append("0123456789ABCDEF"[c shr 4]).append("0123456789ABCDEF"[c and 15])
        }
    }
}

interface AppNavigator {
    /** Opens [route] – a route id from [Routes] or a Flutter route name/title (unknown ones open the Guide). */
    fun go(route: String)
    fun back()
    /** Flutter `context.openFinance([tab])`. */
    fun openFinance(tab: Int = 0) = go(Routes.finance(tab))
}
