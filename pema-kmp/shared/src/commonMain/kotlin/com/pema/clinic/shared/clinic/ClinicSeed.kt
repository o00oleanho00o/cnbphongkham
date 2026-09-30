package com.pema.clinic.shared.clinic

/** Deterministic seed port of `data.js`, `operations-data.js`, CRM and care-finance fixtures. */
object ClinicSeed {
    /** Builds the full web-clinic state used by operations, CRM and Patient 360 screens. */
    fun initial(): ClinicState = withCareFinance(withCrmData(withOperations(initialData()))).deriveCrmTasks()

    internal fun operationsSeedOnly(): ClinicState = withOperations(initialData())

    private fun initialData(): ClinicState {
        val names = listOf(
            "Nguyễn Minh Linh", "Trần Ngọc Anh", "Lê Hoàng Nam", "Phạm Thảo Vy", "Vũ Quỳnh Trang", "Đặng Gia Hân",
            "Bùi Khánh An", "Ngô Đức Minh", "Đỗ Phương Nhi", "Hồ Bảo Ngọc", "Dương Tuấn Kiệt", "Võ Thanh Trúc",
            "Nguyễn Mai Chi", "Trần Quốc Bảo", "Lê Ngọc Diệp", "Phạm Minh Khang", "Vũ Hà My", "Đặng Phương Linh",
            "Bùi Anh Thư", "Ngô Nhật Hạ", "Đỗ Đức Huy", "Hồ Mỹ Duyên", "Dương Thanh Hà", "Võ Tường Vy",
            "Nguyễn Bảo Châu", "Trần Minh Đức", "Lê Hồng Nhung", "Phạm Hải Yến", "Vũ Gia Bảo", "Đặng Ngọc Hân",
            "Bùi Thùy Dương", "Ngô Khánh Vy", "Đỗ Thanh Tùng", "Hồ Lan Anh", "Dương Phúc An", "Võ Minh Châu",
        )
        val groups = listOf(
            ConcernGroup("Nám · tăng sắc tố", "Liệu trình kiểm soát sắc tố", "Chăm sóc & laser theo chỉ định", 5, "SPF 50+ mỗi sáng; thoa lại theo hướng dẫn"),
            ConcernGroup("Mụn viêm", "Theo dõi mụn & chăm sóc tại nhà", "Tái khám và đánh giá đáp ứng", 4, "Sữa rửa mặt dịu nhẹ; tránh tự nặn mụn"),
            ConcernGroup("Thâm sau viêm", "Phục hồi sau mụn", "Chăm sóc da & peel theo chỉ định", 4, "Dưỡng ẩm dịu nhẹ; bảo vệ da khỏi nắng"),
            ConcernGroup("Đỏ da / nhạy cảm", "Phục hồi hàng rào da", "Đánh giá đỏ da định kỳ", 3, "Tránh sản phẩm mới khi chưa hỏi bác sĩ"),
            ConcernGroup("Sẹo sau mụn", "Theo dõi cải thiện sẹo", "Laser phân đoạn theo chỉ định", 5, "Tuân thủ hướng dẫn chăm sóc sau thủ thuật"),
            ConcernGroup("Trẻ hóa da", "Kế hoạch thẩm mỹ cá nhân", "Đánh giá trước thủ thuật", 3, "Theo dõi vùng điều trị theo hướng dẫn"),
        )
        val patients = names.mapIndexed { i, name ->
            val group = groups[i % groups.size]
            val completed = if (i == 0) 2 else 1 + (i % maxOf(1, group.total - 1))
            val visitDate = if (i == 0) "2026-09-06" else if (i % 4 == 0) "2026-08-16" else "2026-09-06"
            val sessions = List(completed) { j ->
                TreatmentSessionRecord(
                    id = "s$i-$j",
                    date = addDays(visitDate, -(completed - 1 - j) * 14),
                    type = group.procedure,
                    note = "Đã ghi nhận đáp ứng và gửi hướng dẫn chăm sóc.",
                    reviewed = true,
                    view = "Chính diện",
                    region = "Mặt",
                    image = "placeholder",
                    aftercare = group.aftercare,
                )
            }
            ClinicPatient(
                id = "P${(i + 1).toString().padStart(3, '0')}",
                name = name,
                age = if (i == 0) 32 else 19 + (i * 7 % 43),
                gender = if (i % 7 == 2) "Nam" else "Nữ",
                phone = "09•• ••• ${100 + i}",
                concern = group.concern,
                plan = group.plan,
                procedure = group.procedure,
                total = group.total,
                completed = completed,
                doctor = if (i % 3 == 2) "BS. Mai" else "BS. Tâm",
                lastVisit = visitDate,
                next = DAY,
                time = "${(9 + i / 4).toString().padStart(2, '0')}:${((i % 4) * 15).toString().padStart(2, '0')}",
                status = when {
                    i == 0 -> "Đang chờ"
                    i % 5 == 1 -> "Đã đến"
                    i % 5 == 2 -> "Đặt hẹn"
                    i % 7 == 0 -> "Vắng hẹn"
                    else -> "Đang điều trị"
                },
                alerts = when {
                    i == 0 -> listOf("Da nhạy cảm", "Theo dõi đỏ da sau điều trị")
                    i % 7 == 0 -> listOf("Cần cập nhật tiền sử dị ứng")
                    else -> emptyList()
                },
                consent = i % 9 != 2,
                photoConsent = true,
                aftercare = group.aftercare,
                meds = listOf(
                    Medication("Sữa rửa mặt dịu nhẹ", "Sáng & tối · theo hướng dẫn đã duyệt"),
                    Medication("Dưỡng ẩm phục hồi", "Sau làm sạch · dùng lượng phù hợp"),
                    Medication("Chống nắng SPF 50+", "Buổi sáng · thoa lại theo hướng dẫn"),
                ),
                notes = "",
                events = listOf(
                    PatientEvent(
                        id = "e$i-1",
                        kind = "followup",
                        date = "2026-09-13",
                        title = "Cập nhật tại nhà đã được xem",
                        detail = if (i == 0) "Đỏ nhẹ khoảng 2 ngày, hiện đã ổn. Không ghi nhận dấu hiệu cảnh báo trong báo cáo." else "Người bệnh báo đã làm theo hướng dẫn chăm sóc.",
                        by = "Điều dưỡng Hương",
                    ),
                    PatientEvent("e$i-2", "session", visitDate, "Hoàn tất buổi $completed/${group.total}", "${group.procedure}. Đã gửi hướng dẫn chăm sóc sau buổi điều trị.", "BS. Tâm"),
                    PatientEvent("e$i-3", "photo", visitDate, "Bộ ảnh theo dõi · chính diện", "Ảnh minh họa giả lập · đồng ý sử dụng trong chăm sóc.", "Điều dưỡng Hương"),
                    PatientEvent("e$i-4", "plan", "2026-06-26", "Bắt đầu ${group.plan.lowercase()}", "Mục tiêu và lịch đánh giá đã được trao đổi với người bệnh.", "BS. Tâm"),
                ),
                messages = listOf(PatientMessage("clinic", "Chào bạn, Pema đã lưu hướng dẫn chăm sóc của buổi điều trị gần nhất. Bạn có thể gửi cập nhật bất cứ lúc nào.", "13/09 · 09:15")),
                sessions = sessions,
                invoices = listOf(Invoice("HD-${(i + 1).toString().padStart(4, '0')}", visitDate, "Buổi chăm sóc / điều trị", 1_200_000 + (i % 4) * 300_000, paid = true)),
            )
        }
        return ClinicState(
            patients = patients,
            followups = listOf(
                FollowUp("F001", "P001", "Ảnh cần bác sĩ xem", "review", "Đỏ nhẹ đã giảm, không đau. Em gửi ảnh trước buổi hẹn.", "2026-09-20T08:42:00", "placeholder", "open", "BS. Tâm"),
                FollowUp("F002", "P004", "Phản hồi triệu chứng", "urgent", "Rát tăng lên sau chăm sóc, muốn được phòng khám gọi lại.", "2026-09-20T08:30:00", null, "open", "BS. Tâm"),
                FollowUp("F003", "P005", "Quá hạn phản hồi 3 ngày", "overdue", "Chưa có phản hồi kiểm tra sau buổi điều trị.", "2026-09-17T09:00:00", null, "open", "CSKH Thu"),
                FollowUp("F004", "P010", "Thiếu ảnh mốc đánh giá", "missing", "Chưa lưu bộ ảnh chính diện của buổi 2.", "2026-09-20T08:00:00", null, "open", "Điều dưỡng Hương"),
                FollowUp("F005", "P007", "Kiểm tra chăm sóc ngày 2", "review", "Da ổn, hơi khô. Đã dùng dưỡng ẩm như hướng dẫn.", "2026-09-20T07:35:00", "placeholder", "open", "CSKH Thu"),
            ),
        )
    }

    private fun withOperations(state: ClinicState): ClinicState {
        val doctors = listOf("BS. Tâm", "BS. Mai", "BS. An", "BS. Lan").mapIndexed { i, name ->
            Doctor("D$i", name, "08:00", "18:00", "12:00", "13:00")
        }
        val rooms = listOf("Khám da liễu", "Tư vấn chuyên sâu", "Laser & thủ thuật", "Chăm sóc da").mapIndexed { i, name -> Room("R$i", name) }
        val services = listOf(
            Service("S0", "Tái khám & đánh giá", 30, 0, 300_000, rooms = listOf("R0", "R1")),
            Service("S1", "Tư vấn da liễu", 45, 15, 500_000, rooms = listOf("R0", "R1")),
            Service("S2", "Laser theo chỉ định", 45, 15, 2_500_000, rooms = listOf("R2")),
            Service("S3", "Chăm sóc theo chỉ định", 45, 15, 1_200_000, rooms = listOf("R3")),
        )
        val appointments = buildList {
            for (day in 0 until 7) {
                for (i in 0 until if (day == 0) 36 else 8) {
                    val n = i % 4
                    val slot = i / 4
                    val hour = 8 + slot + if (slot >= 4) 1 else 0
                    val patient = state.patients[(i + day * 5) % state.patients.size]
                    val service = services[n]
                    add(
                        Appointment(
                            id = "A$day-$i",
                            patient = patient.id,
                            doctor = doctors[n].id,
                            room = rooms[n].id,
                            service = service.id,
                            date = addDays(DAY, day),
                            time = time(hour * 60),
                            duration = service.duration,
                            buffer = service.buffer,
                            price = service.price,
                            status = "booked",
                            note = "Lịch giả lập để thử điều phối",
                        ),
                    )
                }
            }
        }
        val patients = state.patients.toMutableList()
        for (i in 0 until 12) {
            val service = services[i % 4]
            patients[i] = patients[i].copy(
                invoices = patients[i].invoices + Invoice(
                    id = "HD-DEMO-${(i + 1).toString().padStart(3, '0')}",
                    date = DAY,
                    label = service.name,
                    amount = service.price,
                    received = if (i % 3 == 0) service.price / 2 else 0,
                    paid = false,
                ),
            )
        }
        for (a in appointments.filter { it.date == DAY }) {
            val index = patients.indexOfFirst { it.id == a.patient }
            val doctor = doctors.first { it.id == a.doctor }.name
            patients[index] = patients[index].copy(time = a.time, doctor = doctor)
        }
        return state.copy(
            patients = patients,
            operations = ClinicOperations(
                doctors = doctors,
                rooms = rooms,
                services = services,
                appointments = appointments,
                waitlist = patients.take(6).mapIndexed { i, p ->
                    WaitlistEntry("W$i", p.id, "S${i % 4}", if (i % 2 == 1) "Ưu tiên buổi chiều" else "Có thể đến trong ngày", "waiting")
                },
                blocks = listOf(RoomBlock("B1", "R2", "", "2026-09-21", "14:00", "15:00", "Bảo trì thiết bị laser")),
            ),
        )
    }

    private fun withCrmData(state: ClinicState): ClinicState {
        var nextState = state.copy(
            crmAutomationRules = crmRules(),
            crmSegments = listOf("new", "returning", "treating", "dormant", "reactivated"),
            patients = state.patients.mapIndexed { i, p ->
                p.copy(
                    crm = p.crm.copy(
                        source = listOf("Giới thiệu", "Zalo OA", "Tại phòng khám")[i % 3],
                        owner = if (i % 2 == 1) "CSKH Mai Anh" else "CSKH Thu",
                        firstContactAt = "2026-06-26",
                        recommendationAt = p.next,
                        expectedVisitReason = "Bác sĩ hẹn đánh giá",
                        expectedVisitSource = "doctor_recommendation",
                        marketingOptOut = false,
                    ),
                )
            },
        )
        nextState = applyCrmFixtureCases(nextState)
        return appendMobileCases(nextState)
    }

    private fun applyCrmFixtureCases(state: ClinicState): ClinicState {
        val patients = state.patients.toMutableList()
        val appointments = state.operations.appointments.toMutableList()
        val cases = listOf(
            Triple("P025", "01 · Sau Laser CO2 D+1", 1),
            Triple("P026", "02 · D+3 gửi ảnh", 3),
            Triple("P027", "03 · Quá hạn 14 ngày", 30),
            Triple("P028", "04 · Vắng hẹn 2 ngày", 35),
            Triple("P029", "05 · Còn 3/6 buổi, vắng 60 ngày", 60),
            Triple("P030", "06 · Khách cũ 180 ngày", 180),
            Triple("P031", "07 · Gọi lại → đặt lịch", 95),
            Triple("P032", "08 · Sinh nhật tuần này", 7),
        )
        for ((id, label, age) in cases) {
            val index = patients.indexOfFirst { it.id == id }
            var p = patients[index]
            val last = addDays(DAY, -age)
            val adjustedSessions = p.sessions.mapIndexed { i, session -> session.copy(date = addDays(last, -14 * (p.sessions.size - 1 - i))) }.toMutableList()
            var crm = p.crm.copy(demoCase = label, recommendationAt = addDays(last, 30))
            var procedure = p.procedure
            if (id in setOf("P025", "P026", "P032")) {
                val lastIndex = adjustedSessions.lastIndex
                adjustedSessions[lastIndex] = adjustedSessions[lastIndex].copy(protocolId = "laser-co2", type = "Laser CO2 theo chỉ định")
                procedure = "Laser CO2 theo chỉ định"
            }
            if (id == "P027") crm = crm.copy(recommendationAt = addDays(DAY, -14))
            if (id == "P032") crm = crm.copy(birthday = "1996-09-23")
            p = p.copy(
                crm = crm,
                lastVisit = last,
                sessions = adjustedSessions,
                procedure = procedure,
                events = p.events.filterNot { it.kind in setOf("session", "photo", "followup") } +
                    PatientEvent("CASE-$id", "session", last, "Buổi điều trị gần nhất", "$label · dữ liệu tổng hợp", p.doctor),
            )
            if (id == "P029") {
                p = p.copy(
                    total = 6,
                    completed = 3,
                    sessions = List(3) { i ->
                        TreatmentSessionRecord("CRM-S29-$i", addDays(last, -(2 - i) * 30), "Laser theo chỉ định", note = "Buổi tổng hợp", reviewed = true, aftercare = p.aftercare)
                    },
                )
            }
            if (id in setOf("P027", "P028", "P029", "P030", "P031")) {
                for (aIndex in appointments.indices) {
                    val a = appointments[aIndex]
                    if (a.patient == id) {
                        appointments[aIndex] = a.copy(
                            status = "cancelled",
                            cancelReason = "Case CRM: chưa chọn được lịch quay lại",
                            date = addDays(DAY, -2),
                            cancelledAt = "${addDays(DAY, -2)}T09:00:00+07:00",
                        )
                    }
                }
                p = p.copy(next = null, time = "")
            }
            if (id == "P028") {
                val first = appointments.indexOfFirst { it.patient == id }
                if (first >= 0) appointments[first] = appointments[first].copy(status = "missed")
            }
            patients[index] = p
        }
        return state.copy(patients = patients, operations = state.operations.copy(appointments = appointments))
    }

    private fun appendMobileCases(state: ClinicState): ClinicState {
        val names = listOf("Nguyễn Ánh Dương", "Trần Minh Châu", "Lê Bảo Ngọc", "Phạm Gia Linh", "Vũ Thanh Mai", "Đặng Hoàng Yến", "Bùi Ngọc Hà", "Ngô Hải Anh", "Đỗ Thu Hương", "Hồ Khánh Chi")
        val ages = listOf(1, 3, 7, 30, 44, 35, 60, 95, 185, 10)
        val patients = state.patients.toMutableList()
        val appointments = state.operations.appointments.toMutableList()
        for ((i, rule) in state.crmAutomationRules.withIndex()) {
            var n = 37 + i
            while (patients.any { it.id == "P${n.toString().padStart(3, '0')}" }) n++
            val id = "P${n.toString().padStart(3, '0')}"
            val last = addDays(DAY, -ages[i])
            val doctor = if (i % 2 == 1) "BS. Mai" else "BS. Tâm"
            val procedure = if (i < 3) "Laser CO2 theo chỉ định" else "Chăm sóc theo chỉ định"
            val aftercare = "Tuân thủ hướng dẫn đã được bác sĩ trao đổi; liên hệ phòng khám khi cần hỗ trợ."
            val sessions = List(3) { j ->
                TreatmentSessionRecord(
                    id = "MOBILE-$id-$j",
                    date = addDays(last, -(2 - j) * 14),
                    type = procedure,
                    reviewed = true,
                    aftercare = aftercare,
                    protocolId = if (i < 3 && j == 2) "laser-co2" else null,
                )
            }
            patients += ClinicPatient(
                id = id,
                name = names[i],
                phone = "09•• ••• ${237 + i}",
                age = 25 + i,
                gender = "Nữ",
                doctor = doctor,
                status = "Chưa có lịch hôm nay",
                lastVisit = last,
                next = null,
                time = "",
                completed = 3,
                total = 6,
                concern = "Theo dõi da sau điều trị",
                plan = "Kế hoạch chăm sóc da cá nhân",
                procedure = procedure,
                consent = true,
                photoConsent = true,
                aftercare = aftercare,
                notes = "",
                alerts = emptyList(),
                events = listOf(PatientEvent("MOBILE-E-$id", "session", last, "Buổi điều trị gần nhất", "Hồ sơ tổng hợp để kiểm thử chăm sóc.", doctor)),
                invoices = emptyList(),
                meds = emptyList(),
                messages = listOf(PatientMessage("clinic", "Chào bạn, đội ngũ Pema sẵn sàng hỗ trợ hành trình chăm sóc của bạn.", "20/09 · 09:00")),
                sessions = sessions,
                crm = CrmInfo(
                    source = "Tài khoản mẫu mobile",
                    owner = if (i % 2 == 1) "CSKH Mai Anh" else "CSKH Thu",
                    firstContactAt = addDays(last, -30),
                    recommendationAt = when (i) {
                        3 -> DAY
                        4 -> addDays(DAY, -14)
                        else -> addDays(last, 30)
                    },
                    expectedVisitReason = "Bác sĩ hẹn đánh giá",
                    expectedVisitSource = "doctor_recommendation",
                    marketingOptOut = false,
                    demoCase = rule.name,
                    demoGroup = rule.id,
                    birthday = if (i == 9) "1996-09-23" else null,
                ),
            )
            if (rule.id == "no_show") {
                appointments += Appointment("MOBILE-A-$id", id, if (i % 2 == 1) "D1" else "D0", "R1", state.operations.services[0].id, addDays(DAY, -2), "10:00", 30, 10, state.operations.services[0].price, "missed", missedAt = "${addDays(DAY, -2)}T10:00:00+07:00")
            }
        }
        return state.copy(patients = patients, operations = state.operations.copy(appointments = appointments))
    }

    private fun withCareFinance(state: ClinicState): ClinicState {
        val patients = state.patients.mapIndexed { index, p ->
            val plans = if (p.servicePlans.isEmpty()) listOf(makePlan(p, index, state.operations.services)) else p.servicePlans
            val prescriptions = if (p.prescriptions.isEmpty()) makePrescription(p, index)?.let(::listOf).orEmpty() else p.prescriptions
            val deposits = if (p.depositLedger.isEmpty() && index == 0) listOf(DepositEntry("DEP-P001", 4_000_000, 4_000_000, "2026-08-22", "Chuyển khoản")) else p.depositLedger
            p.copy(servicePlans = plans, prescriptions = prescriptions, depositLedger = deposits)
        }
        return state.copy(patients = patients)
    }

    private fun makePlan(p: ClinicPatient, index: Int, catalog: List<Service>): ServicePlan {
        val procedure = p.procedure.lowercase()
        val service = catalog.find { it.name == p.procedure }
            ?: catalog.find { procedure.contains("laser") && it.id == "S2" }
            ?: catalog.find { procedure.contains("chăm sóc") && it.id == "S3" }
            ?: catalog.find { procedure.contains("tái khám") && it.id == "S0" }
            ?: catalog.find { procedure.contains("tư vấn") && it.id == "S1" }
            ?: catalog[index % catalog.size]
        val listPrice = service.price * p.total
        val discount = if (index == 0) 500_000 else if (index % 4 == 0) 300_000 else 0
        val agreed = maxOf(0, listPrice - discount)
        return ServicePlan("LP-${p.id}", service.id, service.name, p.total, p.completed, listPrice, discount, agreed, if (index == 0) 4_000_000 else 0, if (p.completed >= p.total) "completed" else "active", "2026-06-26", p.doctor, p.invoices.map { it.id })
    }

    private fun makePrescription(p: ClinicPatient, index: Int): Prescription? {
        if (index % 5 == 1) {
            return Prescription(
                id = "DT-${p.id}",
                status = "draft",
                prescribedAt = DAY,
                doctor = p.doctor,
                indication = "Đang chờ bác sĩ kiểm tra trước khi gửi",
                items = listOf(PrescriptionItem("Cicaderm Cream 40ml", "Bôi lớp mỏng", "Sáng và tối", "14 ngày", 1, "tuýp")),
            )
        }
        if (index % 3 != 0 && index != 0) return null
        return Prescription(
            id = "DT-${p.id}",
            status = "approved",
            prescribedAt = p.lastVisit ?: DAY,
            doctor = p.doctor,
            reviewedBy = p.doctor,
            reviewedAt = p.lastVisit ?: DAY,
            indication = "Chăm sóc và phục hồi sau buổi điều trị",
            items = listOf(
                PrescriptionItem("Cicaderm Cream 40ml", "Bôi lớp mỏng vùng cần chăm sóc", "Sáng và tối", "14 ngày", 1, "tuýp"),
                PrescriptionItem("Fudareus B 15g", "Bôi theo vùng bác sĩ đã dặn", "Buổi tối", "7 ngày", 1, "tuýp"),
            ),
        )
    }

    private fun crmRules(): List<CrmRule> = listOf(
        CrmRule("d1", "Sau thủ thuật D+1", "session_completed", 1, "Hỏi tình trạng sau thủ thuật", "high", conditions = CrmRuleConditions(protocol = "laser-co2")),
        CrmRule("d3", "D+3 cần ảnh", "session_completed", 3, "Mời gửi cập nhật/ảnh có đồng ý qua Patient Mobile", "high", conditions = CrmRuleConditions(protocol = "laser-co2")),
        CrmRule("d7", "D+7 bác sĩ review", "session_completed", 7, "Chuyển bác sĩ xem ảnh và phản hồi", "high", conditions = CrmRuleConditions(protocol = "laser-co2")),
        CrmRule("due", "Đến hạn tái khám", "expected_visit", 0, "Xác nhận kế hoạch tái khám", "normal"),
        CrmRule("overdue", "Quá hạn tái khám", "expected_visit", 1, "Hỏi trở ngại và hỗ trợ đặt lại lịch", "high"),
        CrmRule("no_show", "Vắng/hủy chưa đặt lại", "appointment_missed", 1, "Liên hệ hỗ trợ chọn lịch mới", "high"),
        CrmRule("abandoned", "Nguy cơ bỏ liệu trình", "remaining_sessions", 45, "Trao đổi về các buổi còn lại", "high"),
        CrmRule("dormant90", "90 ngày chưa quay lại", "last_visit", 90, "Hỏi thăm nhu cầu chăm sóc", "normal", conditions = CrmRuleConditions(marketing = true)),
        CrmRule("dormant180", "180 ngày chưa quay lại", "last_visit", 180, "Chăm sóc lại khách cũ", "high", conditions = CrmRuleConditions(marketing = true)),
        CrmRule("birthday", "Sinh nhật trong tuần", "birthday", 7, "Chúc mừng sinh nhật, không gửi tự động", "low", conditions = CrmRuleConditions(marketing = true)),
    )

    private data class ConcernGroup(val concern: String, val plan: String, val procedure: String, val total: Int, val aftercare: String)
}

internal fun ClinicState.deriveCrmTasks(existing: List<CrmTask> = crmTasks): ClinicState {
    var refreshed = refreshCrm()
    val candidates = buildList {
        for (p in refreshed.patients) {
            val profile = refreshed.crmProfile(p)
            val future = refreshed.upcoming(p)
            val latest = p.sessions.maxByOrNull { it.date }
            for (rule in refreshed.crmAutomationRules) {
                fun addTask(source: String, due: String, appointmentId: String? = null, planId: String? = null) {
                    if (!rule.active || (rule.conditions.marketing && p.crm.marketingOptOut)) return
                    add(
                        CrmTask(
                            id = "CRM:${rule.id}:${p.id}:$source",
                            patientId = p.id,
                            ruleId = rule.id,
                            type = rule.id,
                            reason = rule.name,
                            priority = rule.priority,
                            createdAt = "${DAY}T08:00:00+07:00",
                            dueAt = "${due}T09:00:00+07:00",
                            status = "open",
                            owner = if (rule.id == "d7") p.doctor else p.crm.owner,
                            suggestedAction = rule.suggestedAction,
                            sourceEventId = source,
                            relatedAppointmentId = appointmentId,
                            relatedPlanId = planId,
                        ),
                    )
                }
                if (rule.id in setOf("d1", "d3", "d7") && latest?.protocolId == "laser-co2" && daysBetween(latest.date) in 0..45) {
                    addTask(latest.id, addDays(latest.date, rule.delayDays))
                }
                if (rule.id == "due" && profile.expectedNextVisitAt == DAY && future.none { it.date == DAY && it.status in setOf("arrived", "in_progress") }) {
                    addTask(profile.expectedNextVisitAt ?: DAY, DAY)
                }
                if (rule.id == "overdue" && profile.overdueDays > 0) {
                    addTask(profile.expectedNextVisitAt ?: p.lastVisit ?: DAY, profile.expectedNextVisitAt ?: DAY)
                }
                if (rule.id == "no_show" && future.isEmpty()) {
                    val appointment = refreshed.operations.appointments
                        .filter { it.patient == p.id && it.status in setOf("missed", "cancelled") }
                        .filter { daysBetween((it.cancelledAt ?: it.missedAt ?: "${it.date}T${it.time}:00+07:00").take(10)) >= 1 }
                        .maxByOrNull { it.date }
                    if (appointment != null) addTask(appointment.id, addDays((appointment.cancelledAt ?: appointment.date).take(10), 1), appointment.id)
                }
                if (rule.id == "abandoned" && profile.remaining > 0 && profile.age > rule.delayDays && future.isEmpty()) {
                    addTask(latest?.id ?: p.lastVisit ?: DAY, addDays(p.lastVisit ?: DAY, rule.delayDays), planId = p.servicePlans.firstOrNull()?.id ?: "LP-${p.id}")
                }
                if ((rule.id == "dormant90" && profile.age >= 90 && profile.age < 180 && future.isEmpty()) || (rule.id == "dormant180" && profile.age >= 180 && future.isEmpty())) {
                    addTask(p.lastVisit ?: DAY, addDays(p.lastVisit ?: DAY, rule.delayDays))
                }
                if (rule.id == "birthday" && p.crm.birthday != null) {
                    val birthdayThisYear = DAY.take(4) + p.crm.birthday.substring(4)
                    val birthday = if (birthdayThisYear < DAY) "${DAY.take(4).toInt() + 1}${p.crm.birthday.substring(4)}" else birthdayThisYear
                    if (daysBetween(DAY, birthday) <= rule.delayDays) addTask(birthday, birthday)
                }
            }
        }
    }
    val candidateIds = candidates.map { it.id }.toSet()
    val existingById = existing.associateBy { it.id }
    val merged = buildList {
        candidates.forEach { add(existingById[it.id] ?: it) }
        existing.filter { it.id !in candidateIds }.forEach { task ->
            add(
                if (task.status in setOf("open", "rescheduled") && task.ruleId != "manual")
                    task.copy(status = "superseded", resolution = "Nguồn đã đổi: có lịch mới, mốc mới hoặc opt-out", resolvedAt = "${DAY}T09:00:00+07:00")
                else task,
            )
        }
    }
    refreshed = refreshed.copy(crmTasks = merged)
    return refreshed
}

internal data class CrmProfile(
    val expectedNextVisitAt: String?,
    val expectedVisitSource: String,
    val expectedVisitReason: String,
    val overdueDays: Int,
    val lifecycleStage: String,
    val remaining: Int,
    val riskLevel: String,
    val age: Int,
)

internal fun ClinicState.crmProfile(p: ClinicPatient): CrmProfile {
    val next = upcoming(p).firstOrNull()
    val expected = next?.date ?: p.crm.recommendationAt
    val age = p.lastVisit?.let { daysBetween(it) } ?: 0
    val remaining = maxOf(0, p.total - p.completed)
    val overdue = expected?.let { maxOf(0, daysBetween(it)) } ?: 0
    val lifecycle = when {
        p.crm.reactivatedAt != null -> "reactivated"
        p.sessions.isEmpty() -> "new"
        age >= 90 -> "dormant"
        remaining > 0 -> "treating"
        else -> "returning"
    }
    val risk = if (next == null && (overdue > 7 || (remaining > 0 && age > 45))) "high" else "normal"
    return CrmProfile(
        expectedNextVisitAt = expected,
        expectedVisitSource = if (next != null) "appointment" else p.crm.expectedVisitSource,
        expectedVisitReason = if (next != null) "Lịch hẹn đã xác nhận với phòng khám" else p.crm.expectedVisitReason,
        overdueDays = overdue,
        lifecycleStage = lifecycle,
        remaining = remaining,
        riskLevel = risk,
        age = age,
    )
}

internal fun ClinicState.refreshCrm(): ClinicState {
    val patients = patients.map { patient ->
        var p = patient
        val reception = operations.appointments.find { it.patient == p.id && it.date == DAY && it.isActive() }
        p = p.copy(
            status = reception?.let {
                mapOf("booked" to "Đặt hẹn", "confirmed" to "Đã xác nhận", "arrived" to "Đang chờ", "in_progress" to "Đang điều trị", "completed" to "Hoàn tất")[it.status] ?: "Đặt hẹn"
            } ?: "Chưa có lịch hôm nay",
        )
        val latest = p.sessions.maxByOrNull { it.date }
        if (latest != null && latest.protocolId == "laser-co2" && p.crm.lastProtocolSession != latest.id) {
            p = p.copy(
                crm = p.crm.copy(
                    recommendationAt = addDays(latest.date, 30),
                    expectedVisitSource = "service_protocol",
                    expectedVisitReason = "Đánh giá D+30 sau Laser CO2",
                    lastProtocolSession = latest.id,
                ),
            )
        }
        val profile = crmProfile(p)
        p = p.copy(
            crm = p.crm.copy(
                expectedNextVisitAt = profile.expectedNextVisitAt,
                overdueDays = profile.overdueDays,
                lifecycleStage = profile.lifecycleStage,
                riskLevel = profile.riskLevel,
                lastVisitAt = p.lastVisit,
            ),
            servicePlans = p.servicePlans.map { plan ->
                if (plan.economics != null) plan else plan.copy(economics = PlanEconomics(doctor = plan.doctor.ifBlank { p.doctor }, serviceValue = plan.agreedPrice))
            },
        )
        p
    }
    return copy(patients = patients)
}

internal fun ClinicState.upcoming(p: ClinicPatient): List<Appointment> =
    operations.appointments.filter { it.patient == p.id && it.isActive() && it.status != "completed" && it.date >= DAY }
        .sortedWith(compareBy<Appointment> { it.date }.thenBy { it.time })

internal fun Appointment.isActive(): Boolean = status !in setOf("cancelled", "missed")
