package com.pema.clinic.shared.clinic

import com.pema.clinic.shared.catalog.sampleCatalog
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ClinicSeedParityTest {
    @Test
    fun seedPatientsMatchBundledWebProfiles() {
        val state = ClinicSeed.initial()
        val profiles = sampleCatalog().profiles
        assertEquals(46, state.patients.size)
        assertEquals(profiles.map { it.id }, state.patients.map { it.id })

        for (profile in profiles) {
            val patient = state.patient(profile.id)
            assertEquals(profile.name, patient.name, profile.id)
            assertEquals(profile.doctor, patient.doctor, profile.id)
            assertEquals(profile.sessions, patient.completed, profile.id)
            assertEquals(profile.totalSessions, patient.total, profile.id)
            assertEquals(profile.appointment, patient.time, profile.id)
            assertEquals(profile.day, patient.next ?: "", profile.id)

            val expectedTasks = profile.tasks.map { Triple(it.id, it.type, it.status) }.toSet()
            val actualTasks = state.crmQueue(patient = profile.id).map { Triple(it.id, it.type, it.status) }.toSet()
            assertEquals(expectedTasks, actualTasks, "CRM tasks for ${profile.id}")
        }
    }

    @Test
    fun operationsCountsAndCrmEditsMatchWebSeed() {
        val beforeCrm = ClinicSeed.operationsSeedOnly()
        assertEquals(84, beforeCrm.operations.appointments.size)
        assertEquals(36, beforeCrm.operations.appointments.count { it.date == DAY })
        for (offset in 1..6) {
            assertEquals(8, beforeCrm.operations.appointments.count { it.date == addDays(DAY, offset) }, "D+$offset")
        }

        val state = ClinicSeed.initial()
        assertEquals(85, state.operations.appointments.size)
        assertEquals(31, state.operations.appointments.count { it.date == DAY })
        assertEquals(12, state.operations.appointments.count { it.status == "cancelled" })
        assertEquals(2, state.operations.appointments.count { it.status == "missed" })
        assertEquals(46, state.patients.size)
        assertEquals(5, state.followups.count { it.status == "open" })
    }

    @Test
    fun validateUsesWebErrorMessages() {
        val state = ClinicSeed.initial()

        assertEquals(
            "Ngoài ca bác sĩ hoặc trùng giờ nghỉ 12:00–13:00.",
            assertFailsWith<ClinicError> {
                state.validate(Appointment("X1", "P001", "D0", "R0", "S0", DAY, "11:45", 30, 0, 300_000, "booked"))
            }.message,
        )
        assertEquals(
            "Phòng không phù hợp với dịch vụ đã chọn.",
            assertFailsWith<ClinicError> {
                state.validate(Appointment("X2", "P001", "D0", "R0", "S2", DAY, "16:30", 45, 15, 2_500_000, "booked"))
            }.message,
        )
        assertEquals(
            "Trùng thời gian khóa: Bảo trì thiết bị laser",
            assertFailsWith<ClinicError> {
                state.validate(Appointment("X3", "P001", "D2", "R2", "S2", "2026-09-21", "14:30", 45, 15, 2_500_000, "booked"))
            }.message,
        )
        assertEquals(
            "Trùng bác sĩ với lịch 08:00 của Nguyễn Minh Linh.",
            assertFailsWith<ClinicError> {
                state.validate(Appointment("X4", "P002", "D0", "R1", "S1", DAY, "08:00", 45, 15, 500_000, "booked"))
            }.message,
        )
    }

    @Test
    fun operationsCommandsKeepStateAtomicAndValidateLimits() {
        val store = ClinicStore()
        val before = store.state.value

        assertEquals(
            "Số tiền phải lớn hơn 0 và không vượt số còn lại.",
            assertFailsWith<ClinicError> { store.pay("P001", "HD-DEMO-001", 999_999, "Tiền mặt") }.message,
        )
        assertEquals(before, store.state.value)

        store.pay("P001", "HD-DEMO-001", 150_000, "Chuyển khoản")
        val invoice = store.patient("P001").invoices.first { it.id == "HD-DEMO-001" }
        assertTrue(invoice.paid)
        assertEquals(1, store.state.value.operations.payments.size)

        assertEquals(
            "Có lịch hẹn trong khoảng này. Hãy dời lịch trước khi khóa phòng.",
            assertFailsWith<ClinicError> {
                store.block(RoomBlock("", "R0", "", DAY, "08:00", "09:00", "Khóa thử"))
            }.message,
        )
        assertEquals(
            "Kiểm tra tên, thời lượng 15–180 phút, đệm 0–60 phút và giá không âm.",
            assertFailsWith<ClinicError> {
                store.updateService("S0", ServiceUpdate("", 10, 0, 0, true, listOf("R0")))
            }.message,
        )
    }

    @Test
    fun briefDatesAndMoneyMatchPrototype() {
        val state = ClinicSeed.initial()
        val p001 = state.patient("P001")
        assertEquals("20/9/2026", viDate(DAY))
        assertEquals("1.200.000 ₫", money(1_200_000))
        assertEquals("ML", initials("Nguyễn Minh Linh"))
        assertEquals(
            "Nguyễn Minh Linh, 32 tuổi, quay lại để đánh giá nám · tăng sắc tố. " +
                "Đã hoàn tất 2/5 buổi của liệu trình kiểm soát sắc tố. " +
                "Lần gần nhất: 6/9/2026. Đỏ nhẹ khoảng 2 ngày, hiện đã ổn. Không ghi nhận dấu hiệu cảnh báo trong báo cáo. " +
                "Có 1 mục theo dõi chưa xử lý; cần kiểm tra trước buổi tiếp theo. " +
                "Bước tiếp theo: bác sĩ đánh giá đáp ứng, xác nhận dữ liệu và quyết định kế hoạch.",
            brief(state, p001),
        )
        val finance = state.careFinanceSummary("P001")
        assertEquals(4_000_000, finance.depositAllocated)
        assertTrue(finance.plans.first().due >= 0)
    }
}
