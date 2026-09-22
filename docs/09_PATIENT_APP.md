# Patient mobile experience

## North-star loop
Treatment today → app shows what happened → aftercare/medication with acknowledgement → reminder before follow-up → patient sends a photo/update → clinic acknowledges and responds → timeline/next appointment updates.

## Information architecture
Home (next action + reassurance), Appointments, Journey (milestones and session cards), Progress (consented image sets), Aftercare, Medication, Send Update (symptom/photo + consent), Messages, Documents, Profile.

## Interaction rules
- One primary action per screen; Vietnamese plain language.
- Show “đã gửi / đang được phòng khám xem / đã phản hồi”, never imply real-time emergency service.
- Ask permission before camera/photo; explain who can see it and why.
- Make aftercare scannable; link each instruction to session/date.
- Patient controls sharing of progress photos separately from care photos.

## Success measures
Activation after session; aftercare acknowledgement; update completion; median clinic response time; follow-up attendance. Do not use vanity downloads.


## Current prototype boundary

Patient Mobile displays and confirms a clinic-created appointment. It does not provide patient self-service slot search, booking or rescheduling; the patient can send a message to request help. Clinic staff create/edit appointments from Clinic Web. This is a deliberate demo limitation, not a claim that a production patient app should omit booking.


## Bổ sung Flutter template — 22/09/2026

Patient Mobile web và Flutter Care là hai runtime khác nhau. Care có Trang chủ / Hành trình / Tin nhắn / Hồ sơ, đọc chung DemoStore với Clinic trong một instance; không sync localStorage web. Đơn approved theo patient đã hiển thị; lịch, aftercare và phản hồi còn dùng state chung. Ảnh là placeholder, không upload file. North-star loop ở trên là mục tiêu sản phẩm, chưa được native thực hiện đầy đủ. [Màn và hướng dẫn](NATIVE-TEMPLATE.md), [giới hạn từng chức năng](22_NATIVE_PARITY_AND_VALIDATION.md).
