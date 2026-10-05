# ported from: src/zalo/payload-anomaly-watch.test.ts
from __future__ import annotations

from typing import Any

from pema.channels.payload_anomaly_watch import detect_payload_anomalies, report_payload_anomalies
from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotUpdate
from pema.channels.zalo_bot.zalo_bot_update_parser import doi_update_sang_parsed_message
from pema_contracts.channel import InboundImage, InboundMessage
from pema_contracts.testing import make_inbound


def make_message(**overrides: Any) -> InboundMessage:
    return make_inbound("hi", account_id="acc-1", thread_id="thread-1", sender_id="user-1", **overrides)


# ------------------------------------------------------------------------------ detectPayloadAnomalies


def test_payload_binh_thuong_khong_canh_bao_gi() -> None:
    """payload bình thường không cảnh báo gì"""
    assert detect_payload_anomalies(make_message()) == []


def test_thieu_thread_id_day_la_ca_bot_bo_tin_lang_le_nen_phai_bat_duoc() -> None:
    """thiếu threadId - đây là ca bot bỏ tin lặng lẽ nên phải bắt được"""
    anomalies = detect_payload_anomalies(make_inbound("hi", thread_id=""))
    assert len(anomalies) == 1
    assert "threadId" in anomalies[0]


def test_thieu_uid_from_ma_khong_phai_tin_cua_bot() -> None:
    """thiếu uidFrom mà không phải tin của bot"""
    anomalies = detect_payload_anomalies(make_inbound("hi", sender_id=""))
    assert "uidFrom" in anomalies[0]


def test_tin_cua_chinh_bot_thieu_uid_from_la_binh_thuong_khong_canh_bao() -> None:
    """tin của chính bot thiếu uidFrom là bình thường, không cảnh báo"""
    assert detect_payload_anomalies(make_inbound("hi", sender_id="", is_self=True)) == []


def test_msg_type_la_photo_nhung_khong_moi_duoc_url_dau_hieu_zalo_doi_ten_field() -> None:
    """msgType là photo nhưng không moi được URL - dấu hiệu Zalo đổi tên field"""
    anomalies = detect_payload_anomalies(make_message(raw={"msgType": "chat.photo"}, images=[]))
    assert len(anomalies) == 1
    assert "đổi tên field" in anomalies[0]


def test_photo_co_url_thi_im_lang() -> None:
    """photo có URL thì im lặng"""
    msg = make_message(raw={"msgType": "chat.photo"}, images=[InboundImage(url="https://z.test/a.jpg")])
    assert detect_payload_anomalies(msg) == []


def test_tin_khong_phai_anh_ma_khong_co_images_la_binh_thuong() -> None:
    """tin không phải ảnh mà không có images là bình thường"""
    assert detect_payload_anomalies(make_message(raw={"msgType": "webchat"}, images=[])) == []


def test_nhieu_bat_thuong_cung_luc_thi_bao_het() -> None:
    """nhiều bất thường cùng lúc thì báo hết"""
    msg = make_inbound("hi", thread_id="", sender_id="", raw={"msgType": "chat.photo"})
    assert len(detect_payload_anomalies(msg)) == 3


def test_bat_duoc_dung_ca_payload_rong_di_qua_parser_that() -> None:
    """bắt được đúng ca payload rỗng đi qua parser thật"""
    # The shape of a payload when Zalo changes its structure: the parser returns everything empty.
    parsed = doi_update_sang_parsed_message(
        "acc-1", ZaloBotUpdate.model_validate({"event_name": "x", "message": {}})
    )
    assert parsed is not None
    anomalies = detect_payload_anomalies(parsed)
    assert any("threadId" in a for a in anomalies)
    assert any("uidFrom" in a for a in anomalies)


# --------------------------------------------------------------------- reportPayloadAnomalies - chống ngập log

T0 = 1_000_000.0


def test_payload_hong_doi_lien_tuc_chi_log_1_lan_trong_cua_so_10_phut() -> None:
    """payload hỏng dội liên tục chỉ log 1 lần trong cửa sổ 10 phút"""
    msg = make_inbound("hi", thread_id="")

    assert len(report_payload_anomalies("acc-1", msg, T0)) == 1, "lần đầu phải log"
    for i in range(1, 50):
        assert report_payload_anomalies("acc-1", msg, T0 + i * 1000) == [], (
            "trong cửa sổ throttle không được log lại"
        )


def test_het_cua_so_thi_log_lai_de_biet_loi_van_con() -> None:
    """hết cửa sổ thì log lại để biết lỗi vẫn còn"""
    msg = make_inbound("hi", thread_id="")
    report_payload_anomalies("acc-1", msg, T0)

    assert report_payload_anomalies("acc-1", msg, T0 + 9 * 60_000) == []
    assert len(report_payload_anomalies("acc-1", msg, T0 + 11 * 60_000)) == 1


def test_account_khac_nhau_throttle_rieng_1_nick_hong_khong_che_loi_nick_kia() -> None:
    """account khác nhau throttle riêng - 1 nick hỏng không che lỗi nick kia"""
    msg = make_inbound("hi", thread_id="")
    assert len(report_payload_anomalies("acc-1", msg, T0)) == 1
    assert len(report_payload_anomalies("acc-2", msg, T0)) == 1


def test_loai_bat_thuong_khac_nhau_throttle_rieng() -> None:
    """loại bất thường khác nhau throttle riêng"""
    # An empty thread id is logged first, then an image error is added -> the image error must still be
    # logged.
    report_payload_anomalies("acc-1", make_inbound("hi", thread_id=""), T0)
    logged = report_payload_anomalies(
        "acc-1", make_inbound("hi", thread_id="", raw={"msgType": "chat.photo"}), T0 + 1000
    )
    assert len(logged) == 1
    assert "đổi tên field" in logged[0]
