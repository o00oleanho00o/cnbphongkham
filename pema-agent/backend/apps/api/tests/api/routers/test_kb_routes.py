# ported from: src/server/routes/kb-routes.test.ts
"""``/admin/kb`` - CRUD of sources, upload, agent bindings.

Forced deviations: Hono ``app.request`` -> an ASGI client on a FastAPI app with the knowledge router only;
the dashboard password -> a stand-in for the session authentication of package B1 (``conftest``); the paths,
DTOs and statuses are those of the OpenAPI contract (``name``/``text``, ``ids``, ``ErrorCode`` -> 422/404/409/
413, 204 for delete, 401/403 for the missing context/permission). Every test starts from an empty knowledge
base and an empty data directory."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from pema.api.kb_test_support import KbApi
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _tuning_sach() -> Generator[None]:
    reset_tuning_provider()
    yield
    reset_tuning_provider()


def so_nguon(api: KbApi) -> int:
    return int(api.kb_database.scalar("SELECT count(*) FROM agent.kb_document"))


def so_file_tren_dia(api: KbApi) -> int:
    kb_dir = api.data_dir / "kb"
    return len(list(kb_dir.iterdir())) if kb_dir.exists() else 0


def them_doan(api: KbApi, source_id: str, doan: list[tuple[str, str]]) -> None:
    for i, (tieu_de, noi_dung) in enumerate(doan):
        api.kb_database.execute(
            "INSERT INTO agent.kb_chunk (clinic_id, source_id, ord, title, content, folded) "
            "VALUES (:c, :s, :o, :t, :n, :f)",
            {
                "c": api.kb_database.clinic_id,
                "s": source_id,
                "o": i,
                "t": tieu_de,
                "n": noi_dung,
                "f": noi_dung,
            },
        )


async def tao_text(api: KbApi, ten: str = "nguồn", noi_dung: str = "x") -> str:
    res = await api.client.post(
        f"{api.base}/sources/text", json={"name": ten, "text": noi_dung}, headers=api.headers()
    )
    assert res.status_code == 202, res.text
    return str(res.json()["id"])


# ------------------------------------------------------------------------------ POST /sources/file


async def test_post_sources_file_upload_returns_202_and_pending_does_not_block_the_request_to_process(
    kb_api: KbApi,
) -> None:
    """upload trả 202 và trạng thái cho_xu_ly - KHÔNG chặn request để xử lý"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file",
        files={"file": ("gia.txt", "Bảng giá".encode())},
        data={"name": "gia.txt"},
        headers=kb_api.headers(),
    )
    assert res.status_code == 202, res.text
    assert res.json()["status"] == "cho_xu_ly"
    assert res.json()["raw_text"] == ""


async def test_post_sources_file_file_over_the_ceiling_is_refused_with_413_and_nothing_is_written_to_disk(
    kb_api: KbApi,
) -> None:
    """file quá trần bị từ chối bằng 413, KHÔNG ghi gì xuống đĩa"""
    install_tuning_provider(StaticTuningProvider({"KB_MAX_FILE_MB": 1}))
    qua = b"a" * (2 * 1024 * 1024)
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file",
        files={"file": ("to.txt", qua)},
        data={"name": "to.txt"},
        headers=kb_api.headers(),
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "payload_too_large"
    assert so_nguon(kb_api) == 0
    assert so_file_tren_dia(kb_api) == 0


async def test_post_sources_file_pdf_extension_with_content_that_is_not_a_pdf_is_refused(
    kb_api: KbApi,
) -> None:
    """đuôi .pdf nhưng nội dung không phải PDF bị từ chối"""
    # Trusting the extension would open the door to ANY file landing in the data directory
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file",
        files={"file": ("gia.pdf", b"PK\x03\x04 day la zip")},
        data={"name": "gia"},
        headers=kb_api.headers(),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "kb_source_invalid"
    assert so_nguon(kb_api) == 0, "không được tạo dòng DB khi file không hợp lệ"
    assert so_file_tren_dia(kb_api) == 0


async def test_post_sources_file_extension_outside_the_5_supported_formats_is_refused(kb_api: KbApi) -> None:
    """đuôi không nằm trong 5 định dạng hỗ trợ bị từ chối"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file",
        files={"file": ("virus.exe", b"MZ...")},
        data={"name": "virus"},
        headers=kb_api.headers(),
    )
    assert res.status_code == 422


async def test_post_sources_file_missing_file_is_refused(kb_api: KbApi) -> None:
    """thiếu file bị từ chối"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file", data={"name": "x"}, headers=kb_api.headers()
    )
    assert res.status_code == 422


async def test_post_sources_file_over_long_name_is_refused(kb_api: KbApi) -> None:
    """upload file với ten quá dài bị từ chối"""
    # ``file_name`` deliberately differs from the name: otherwise a 201-character file name with no
    # extension would be refused by the FORMAT branch first and the test would go red (or green) for the
    # wrong reason, not for the name ceiling.
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file",
        files={"file": ("gia.txt", b"x")},
        data={"name": "a" * 201},
        headers=kb_api.headers(),
    )
    assert res.status_code == 422
    assert so_nguon(kb_api) == 0


async def test_post_sources_file_name_of_exactly_200_characters_still_passes_pins_the_boundary(
    kb_api: KbApi,
) -> None:
    """ten đúng 200 ký tự VẪN qua - ghim biên, .max(150) cũng sẽ làm test này đỏ"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file",
        files={"file": ("gia.txt", b"x")},
        data={"name": "a" * 200},
        headers=kb_api.headers(),
    )
    assert res.status_code == 202, res.text


@pytest.mark.parametrize(
    ("ten_file", "noi_dung", "dinh_dang"),
    [
        ("gia.pdf", b"%PDF-1.7\nnoi dung gia lap, chi can dung chu ky dau file", "pdf"),
        ("hop-dong.docx", b"PK\x03\x04 noi dung gia lap, chi can dung chu ky dau file", "docx"),
        ("bang-gia.xlsx", b"PK\x03\x04 noi dung gia lap, chi can dung chu ky dau file", "xlsx"),
    ],
)
async def test_post_sources_file_a_real_signature_is_accepted_with_202(
    kb_api: KbApi, ten_file: str, noi_dung: bytes, dinh_dang: str
) -> None:
    """pdf/docx/xlsx với chữ ký thật (%PDF / PK) được chấp nhận, trả 202"""
    # The ACCEPT branch: a failing test (wrong magic bytes) does not prove the accepting branch is wired to
    # the signature table - an implementation that refused 100% of pdf/docx/xlsx would stay green.
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file",
        files={"file": (ten_file, noi_dung)},
        data={"name": ten_file},
        headers=kb_api.headers(),
    )
    assert res.status_code == 202, res.text
    assert res.json()["format"] == dinh_dang


async def test_post_sources_file_without_a_name_the_file_name_is_used(kb_api: KbApi) -> None:
    """(thêm) không gửi tên thì lấy tên file bỏ đuôi"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file", files={"file": ("huong-dan.md", b"# a\n\nb")}, headers=kb_api.headers()
    )
    assert res.status_code == 202
    assert res.json()["name"] == "huong-dan"


# ------------------------------------------------------------------------------ POST /sources/text


async def test_post_sources_text_typed_content_creates_a_text_source_no_file_needed(kb_api: KbApi) -> None:
    """gõ tay nội dung tạo được nguồn loai='text', không cần file nào"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/text",
        json={"name": "Giờ làm việc", "text": "8h - 21h mỗi ngày"},
        headers=kb_api.headers(),
    )
    assert res.status_code == 202
    body = res.json()
    assert body["kind"] == "text"
    assert body["status"] == "cho_xu_ly"
    assert body["path"] == "", "nguồn gõ tay không được sinh file trên đĩa"
    assert so_file_tren_dia(kb_api) == 0


async def test_post_sources_text_empty_content_is_refused(kb_api: KbApi) -> None:
    """gõ tay với nội dung rỗng bị từ chối"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/text", json={"name": "trống", "text": "   "}, headers=kb_api.headers()
    )
    assert res.status_code == 422
    assert so_nguon(kb_api) == 0


async def test_post_sources_text_missing_or_over_long_name_is_refused(kb_api: KbApi) -> None:
    """thiếu tên / tên quá 200 ký tự bị từ chối - ô maxLength ở form chỉ là giao diện"""
    for ten in ("", "a" * 201):
        res = await kb_api.client.post(
            f"{kb_api.base}/sources/text", json={"name": ten, "text": "x"}, headers=kb_api.headers()
        )
        assert res.status_code == 422


async def test_post_sources_text_typed_content_over_the_file_ceiling_is_refused_and_nothing_is_written(
    kb_api: KbApi,
) -> None:
    """nội dung gõ tay quá trần KB_MAX_FILE_MB bị từ chối, KHÔNG ghi gì xuống DB"""
    # The body is gathered into memory BEFORE anything can be checked - it must be cut at the reading
    # layer here too, not only on the file upload route.
    install_tuning_provider(StaticTuningProvider({"KB_MAX_FILE_MB": 1}))
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/text",
        json={"name": "quá khổ", "text": "a" * (2 * 1024 * 1024)},
        headers=kb_api.headers(),
    )
    assert res.status_code == 413
    assert so_nguon(kb_api) == 0, "không được tạo dòng DB khi nội dung vượt trần"


async def test_post_sources_text_the_ceiling_is_also_enforced_without_a_content_length_header(
    kb_api: KbApi,
) -> None:
    """(thêm) trần body cắt cả khi không có Content-Length (chunked)"""
    install_tuning_provider(StaticTuningProvider({"KB_MAX_FILE_MB": 1}))

    async def luong() -> object:
        for _ in range(3):
            yield b'{"name": "x", "text": "' + b"a" * (600 * 1024)

    res = await kb_api.client.post(
        f"{kb_api.base}/sources/text",
        content=luong(),  # type: ignore[arg-type]
        headers={**kb_api.headers(), "content-type": "application/json"},
    )
    assert res.status_code == 413
    assert so_nguon(kb_api) == 0


async def test_post_sources_text_the_response_does_not_echo_the_typed_content(kb_api: KbApi) -> None:
    """response KHÔNG dội nguyên nội dung vừa gõ - client vừa gõ xong, không cần server trả lại"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/text",
        json={"name": "C", "text": "nội dung bí mật dài"},
        headers=kb_api.headers(),
    )
    assert res.json()["raw_text"] == ""
    assert "nội dung bí mật dài" not in res.text


# ------------------------------------------------------------------------------ GET /sources


async def test_get_sources_lists_the_source_just_created_without_its_raw_text(kb_api: KbApi) -> None:
    """liệt kê nguồn vừa tạo; KHÔNG kéo theo noi_dung_goc"""
    await tao_text(kb_api, "A", "nội dung bí mật dài")
    res = await kb_api.client.get(f"{kb_api.base}/sources", headers=kb_api.headers())
    assert res.status_code == 200
    items = res.json()
    assert [i["name"] for i in items] == ["A"]
    assert items[0]["raw_text"] == ""
    assert "nội dung bí mật dài" not in res.text, (
        "trang tự làm mới mỗi vài giây, kéo dư toàn văn là phí băng thông"
    )


# ------------------------------------------------------------------------------ POST /sources/{id}/reindex


async def test_post_reindex_sets_pending_again_and_resets_the_attempts_budget(kb_api: KbApi) -> None:
    """đặt lại cho_xu_ly để xử lý lại, cấp lại budget lượt thử (soLanThu về 0)"""
    id_ = await tao_text(kb_api, "hỏng rồi")
    kb_api.kb_database.execute(
        "UPDATE agent.kb_document SET status = 'hong', error = 'lỗi cũ', attempts = 5 WHERE id = :id",
        {"id": id_},
    )
    res = await kb_api.client.post(f"{kb_api.base}/sources/{id_}/reindex", headers=kb_api.headers())
    assert res.status_code == 200
    assert (res.json()["status"], res.json()["attempts"]) == ("cho_xu_ly", 0)


async def test_post_reindex_unknown_id_returns_404(kb_api: KbApi) -> None:
    """id không tồn tại trả 404"""
    res = await kb_api.client.post(f"{kb_api.base}/sources/khong-ton-tai/reindex", headers=kb_api.headers())
    assert res.status_code == 404


async def test_post_reindex_while_the_source_is_dang_xu_ly_returns_409_not_swallowed_silently(
    kb_api: KbApi,
) -> None:
    """bấm Xử lý lại lúc nguồn đang dang_xu_ly trả 409, không nuốt lặng lẽ (I6)"""
    id_ = await tao_text(kb_api, "đang xử lý", "abc")
    kb_api.kb_database.execute(
        "UPDATE agent.kb_document SET status = 'dang_xu_ly' WHERE id = :id", {"id": id_}
    )
    res = await kb_api.client.post(f"{kb_api.base}/sources/{id_}/reindex", headers=kb_api.headers())
    assert res.status_code == 409
    assert (
        kb_api.kb_database.scalar("SELECT status FROM agent.kb_document WHERE id = :id", {"id": id_})
        == "dang_xu_ly"
    ), (
        "route KHÔNG được đổi trạng thái khi từ chối - lượt đang chạy phải là nơi duy nhất quyết định trạng thái cuối"
    )


async def test_post_reindex_response_does_not_echo_the_full_text(kb_api: KbApi) -> None:
    """response KHÔNG dội nguyên toàn văn - cùng lỗi đã vá ở GET /sources, sót lại ở route này"""
    id_ = await tao_text(kb_api, "n", "nội dung bí mật dài")
    res = await kb_api.client.post(f"{kb_api.base}/sources/{id_}/reindex", headers=kb_api.headers())
    assert "nội dung bí mật dài" not in res.text


# ------------------------------------------------------------------------------ GET chunks / agents of a source


async def test_get_chunks_pages_the_chunks_with_the_heading_breadcrumb(kb_api: KbApi) -> None:
    """trả đoạn có phân trang, kèm breadcrumb tieuDe để tự phát hiện lỗi đọc file"""
    id_ = await tao_text(kb_api, "bảng giá")
    them_doan(kb_api, id_, [("Bảng giá > Combo A", "100.000đ"), ("Bảng giá > Combo B", "150.000đ")])
    res = await kb_api.client.get(
        f"{kb_api.base}/sources/{id_}/chunks?offset=0&limit=20", headers=kb_api.headers()
    )
    assert res.status_code == 200
    assert res.json()[0]["title"] == "Bảng giá > Combo A"


async def test_get_chunks_offset_and_limit_cut_the_right_page(kb_api: KbApi) -> None:
    """offset/limit cắt đúng trang, không trả dư đoạn của trang khác"""
    id_ = await tao_text(kb_api, "nhiều đoạn")
    them_doan(kb_api, id_, [("", f"đoạn {i}") for i in range(5)])
    res = await kb_api.client.get(
        f"{kb_api.base}/sources/{id_}/chunks?offset=2&limit=2", headers=kb_api.headers()
    )
    assert [c["content"] for c in res.json()] == ["đoạn 2", "đoạn 3"]


async def test_get_chunks_limit_over_100_is_refused_it_never_pulls_the_whole_table(kb_api: KbApi) -> None:
    """limit vượt trần (100) bị từ chối, không lọt xuống kéo cả bảng"""
    id_ = await tao_text(kb_api)
    res = await kb_api.client.get(f"{kb_api.base}/sources/{id_}/chunks?limit=101", headers=kb_api.headers())
    assert res.status_code == 422


async def test_get_chunks_unknown_source_returns_404(kb_api: KbApi) -> None:
    """nguồn không tồn tại trả 404"""
    res = await kb_api.client.get(f"{kb_api.base}/sources/khong-ton-tai/chunks", headers=kb_api.headers())
    assert res.status_code == 404


async def test_get_source_agents_returns_the_agents_bound_used_to_warn_before_a_delete(kb_api: KbApi) -> None:
    """trả đúng danh sách agent đang gán nguồn này - dashboard dùng để cảnh báo trước khi xóa"""
    kb_api.kb_database.add_agent("a1")
    kb_api.kb_database.add_agent("a2")
    id_ = await tao_text(kb_api)
    for agent in ("a1", "a2"):
        res = await kb_api.client.put(
            f"{kb_api.base}/agents/{agent}/sources", json={"ids": [id_]}, headers=kb_api.headers()
        )
        assert res.status_code == 200
    res = await kb_api.client.get(f"{kb_api.base}/sources/{id_}/agents", headers=kb_api.headers())
    assert res.status_code == 200
    assert sorted(res.json()["ids"]) == ["a1", "a2"]


async def test_get_source_agents_unknown_source_returns_404_and_unbound_source_returns_empty(
    kb_api: KbApi,
) -> None:
    """nguồn không tồn tại trả 404; nguồn chưa agent nào gán trả mảng rỗng"""
    res = await kb_api.client.get(f"{kb_api.base}/sources/khong-ton-tai/agents", headers=kb_api.headers())
    assert res.status_code == 404
    id_ = await tao_text(kb_api)
    res = await kb_api.client.get(f"{kb_api.base}/sources/{id_}/agents", headers=kb_api.headers())
    assert res.json() == {"ids": []}


# ------------------------------------------------------------------------------ DELETE


async def test_delete_removes_both_the_database_row_and_the_file_on_disk(kb_api: KbApi) -> None:
    """DELETE xóa cả dòng DB lẫn file trên đĩa"""
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/file",
        files={"file": ("x.txt", b"x")},
        data={"name": "xóa thử"},
        headers=kb_api.headers(),
    )
    id_ = res.json()["id"]
    assert so_file_tren_dia(kb_api) == 1, "chưa xóa mà file đã không có thì test vô nghĩa"

    res = await kb_api.client.delete(f"{kb_api.base}/sources/{id_}", headers=kb_api.headers())

    assert res.status_code == 204
    assert so_nguon(kb_api) == 0
    assert so_file_tren_dia(kb_api) == 0, "dòng DB mất nhưng file còn nằm lại - đĩa phình mãi"


async def test_delete_a_typed_source_without_a_file_raises_nothing_and_unknown_id_returns_404(
    kb_api: KbApi,
) -> None:
    """xóa nguồn gõ tay (không có file) không lỗi gì; id không tồn tại trả 404"""
    id_ = await tao_text(kb_api, "text thuần")
    assert (
        await kb_api.client.delete(f"{kb_api.base}/sources/{id_}", headers=kb_api.headers())
    ).status_code == 204
    assert (
        await kb_api.client.delete(f"{kb_api.base}/sources/khong-ton-tai", headers=kb_api.headers())
    ).status_code == 404


# ------------------------------------------------------------------------------ bindings (agent -> sources)


async def test_put_agent_sources_replaces_the_whole_list(kb_api: KbApi) -> None:
    """PUT thay thế toàn bộ danh sách"""
    kb_api.kb_database.add_agent("a1")
    n1, n2 = await tao_text(kb_api, "n1"), await tao_text(kb_api, "n2")
    await kb_api.client.put(
        f"{kb_api.base}/agents/a1/sources", json={"ids": [n1, n2]}, headers=kb_api.headers()
    )
    res = await kb_api.client.put(
        f"{kb_api.base}/agents/a1/sources", json={"ids": [n2]}, headers=kb_api.headers()
    )
    assert res.json() == {"ids": [n2]}
    assert (await kb_api.client.get(f"{kb_api.base}/agents/a1/sources", headers=kb_api.headers())).json() == {
        "ids": [n2]
    }


async def test_put_agent_sources_binding_a_missing_source_or_agent_is_refused_and_writes_nothing(
    kb_api: KbApi,
) -> None:
    """gán nguồn KHÔNG tồn tại / cho agentId KHÔNG tồn tại bị từ chối - không được tạo dòng gán mồ côi"""
    kb_api.kb_database.add_agent("a1")
    n1 = await tao_text(kb_api, "n1")
    res = await kb_api.client.put(
        f"{kb_api.base}/agents/a1/sources", json={"ids": ["khong-co"]}, headers=kb_api.headers()
    )
    assert res.status_code == 422
    res = await kb_api.client.put(
        f"{kb_api.base}/agents/agent-khong-ton-tai/sources", json={"ids": [n1]}, headers=kb_api.headers()
    )
    assert res.status_code == 422
    assert kb_api.kb_database.scalar("SELECT count(*) FROM agent.agent_kb_document") == 0


async def test_put_agent_sources_far_too_many_ids_are_refused_by_the_list_bound_before_any_lookup(
    kb_api: KbApi,
) -> None:
    """sourceIds vượt xa trần số lượng vẫn bị chặn nhờ .max(500) - không lọt xuống tới câu SQL"""
    # 1-character ids: the cheapest valid element (4 bytes of JSON), 40,000 of them is ~160 KB - under the
    # route's own 256 KB body ceiling, so the LIST bound is what is measured, not the body ceiling.
    kb_api.kb_database.add_agent("a1")
    qua = ["a"] * 40_000
    res = await kb_api.client.put(
        f"{kb_api.base}/agents/a1/sources", json={"ids": qua}, headers=kb_api.headers()
    )
    assert res.status_code == 422, f"phải chặn có lý do, không phải văng 500 trần - nhận {res.status_code}"
    assert res.json()["error"]["code"] == "validation_failed"
    assert kb_api.kb_database.scalar("SELECT count(*) FROM agent.agent_kb_document") == 0


async def test_put_agent_sources_a_huge_body_is_cut_at_the_reading_layer(kb_api: KbApi) -> None:
    """PUT gán nguồn với body khổng lồ bị chặn ở TẦNG ĐỌC, không nuốt hết vào RAM"""
    kb_api.kb_database.add_agent("a1")
    ids = ["x" * 8000 for _ in range(400)]
    res = await kb_api.client.put(
        f"{kb_api.base}/agents/a1/sources", json={"ids": ids}, headers=kb_api.headers()
    )
    assert res.status_code == 413


async def test_put_agent_sources_uses_its_own_256kb_ceiling_not_the_file_ceiling(kb_api: KbApi) -> None:
    """PUT gán nguồn dùng trần body RIÊNG (256KB), KHÔNG bám theo trần file 20-100MB"""
    # The file ceiling is left at its default (20 MB): the 1 MB body below passes it - that is exactly what
    # tells the old shared ceiling from the own one.
    kb_api.kb_database.add_agent("a1")
    than = {"ids": ["x" + "y" * (1024 * 1024)]}
    res = await kb_api.client.put(f"{kb_api.base}/agents/a1/sources", json=than, headers=kb_api.headers())
    assert res.status_code == 413, f"body 1MB phải bị trần riêng 256KB chặn - nhận {res.status_code}"
    assert kb_api.kb_database.scalar("SELECT count(*) FROM agent.agent_kb_document") == 0


async def test_put_agent_sources_the_largest_valid_payload_500_ids_still_passes_the_own_ceiling(
    kb_api: KbApi,
) -> None:
    """PUT gán nguồn với payload HỢP LỆ lớn nhất (500 id) vẫn qua được trần riêng"""
    kb_api.kb_database.add_agent("a1")
    kb_api.kb_database.execute(
        "INSERT INTO agent.kb_document (clinic_id, id, name, kind) "
        "SELECT :c, 'nguon-' || lpad(i::text, 12, '0'), 'n' || i, 'text' FROM generate_series(1, 500) AS i",
        {"c": kb_api.kb_database.clinic_id},
    )
    ids = [f"nguon-{i:012d}" for i in range(1, 501)]
    res = await kb_api.client.put(
        f"{kb_api.base}/agents/a1/sources", json={"ids": ids}, headers=kb_api.headers()
    )
    assert res.status_code == 200, (
        f"payload hợp lệ lớn nhất phải qua được - nhận {res.status_code}: {res.text[:200]}"
    )
    assert len(res.json()["ids"]) == 500


async def test_put_agent_sources_each_element_has_its_own_length_ceiling(kb_api: KbApi) -> None:
    """từng phần tử sourceIds có trần độ dài - id thật chỉ dài 16 ký tự hex, 64 đã dư"""
    kb_api.kb_database.add_agent("a1")
    res = await kb_api.client.put(
        f"{kb_api.base}/agents/a1/sources", json={"ids": ["x" * 200]}, headers=kb_api.headers()
    )
    assert res.status_code == 422
    # Not only the status: an unknown 200-character id would ALSO be refused by the "does not exist" branch.
    # The message of the list-bound branch names the 64-character ceiling.
    assert "64" in res.json()["error"]["message"], (
        "phải bị chặn ở trần độ dài phần tử, không phải ở bước kiểm tồn tại"
    )


# ------------------------------------------------------------------------------ bindings (source -> agents)


async def test_put_source_agents_binding_many_agents_reads_back_the_same_in_both_directions(
    kb_api: KbApi,
) -> None:
    """gán nguồn cho nhiều agent, đọc lại thấy đúng ở CẢ HAI chiều"""
    n = await tao_text(kb_api, "Bảng giá")
    kb_api.kb_database.add_agent("ban-hang")
    kb_api.kb_database.add_agent("ho-tro")
    res = await kb_api.client.put(
        f"{kb_api.base}/sources/{n}/agents", json={"ids": ["ban-hang", "ho-tro"]}, headers=kb_api.headers()
    )
    assert res.status_code == 200
    assert res.json() == {"ids": ["ban-hang", "ho-tro"]}
    assert (
        await kb_api.client.get(f"{kb_api.base}/agents/ban-hang/sources", headers=kb_api.headers())
    ).json() == {"ids": [n]}


async def test_put_source_agents_replaces_and_only_touches_this_source(kb_api: KbApi) -> None:
    """THAY THẾ chứ không cộng dồn; chỉ đụng nguồn ĐANG gán, không xóa gán của nguồn khác cùng agent"""
    n1, n2 = await tao_text(kb_api, "Bảng giá"), await tao_text(kb_api, "Chính sách")
    kb_api.kb_database.add_agent("ban-hang")
    await kb_api.client.put(
        f"{kb_api.base}/sources/{n1}/agents", json={"ids": ["ban-hang"]}, headers=kb_api.headers()
    )
    await kb_api.client.put(
        f"{kb_api.base}/sources/{n2}/agents", json={"ids": ["ban-hang"]}, headers=kb_api.headers()
    )
    got = (
        await kb_api.client.get(f"{kb_api.base}/agents/ban-hang/sources", headers=kb_api.headers())
    ).json()["ids"]
    assert sorted(got) == sorted([n1, n2])
    await kb_api.client.put(f"{kb_api.base}/sources/{n1}/agents", json={"ids": []}, headers=kb_api.headers())
    assert (
        await kb_api.client.get(f"{kb_api.base}/sources/{n1}/agents", headers=kb_api.headers())
    ).json() == {"ids": []}


async def test_put_source_agents_unknown_source_is_404_and_unknown_agent_is_refused_without_writing(
    kb_api: KbApi,
) -> None:
    """nguồn không tồn tại thì 404; agent không tồn tại thì từ chối trọn gói và KHÔNG ghi gì cả"""
    kb_api.kb_database.add_agent("co-that")
    res = await kb_api.client.put(
        f"{kb_api.base}/sources/khong-co-that/agents", json={"ids": ["co-that"]}, headers=kb_api.headers()
    )
    assert res.status_code == 404
    n = await tao_text(kb_api, "Bảng giá")
    res = await kb_api.client.put(
        f"{kb_api.base}/sources/{n}/agents",
        json={"ids": ["co-that", "khong-co-that"]},
        headers=kb_api.headers(),
    )
    assert res.status_code == 422
    assert kb_api.kb_database.scalar("SELECT count(*) FROM agent.agent_kb_document") == 0


async def test_put_source_agents_element_length_ceiling_and_huge_body(kb_api: KbApi) -> None:
    """từng phần tử agentIds có trần độ dài; body khổng lồ bị chặn ở TẦNG ĐỌC"""
    n = await tao_text(kb_api, "Bảng giá")
    res = await kb_api.client.put(
        f"{kb_api.base}/sources/{n}/agents", json={"ids": ["x" * 200]}, headers=kb_api.headers()
    )
    assert res.status_code == 422
    ids = ["x" * 8000 for _ in range(400)]
    res = await kb_api.client.put(
        f"{kb_api.base}/sources/{n}/agents", json={"ids": ids}, headers=kb_api.headers()
    )
    assert res.status_code == 413


# ------------------------------------------------------------------------------ approval, search, auth


async def test_patch_approval_only_a_doctor_or_the_owner_may_sign_off_and_it_records_who(
    kb_api: KbApi,
) -> None:
    """(thêm) chỉ bác sĩ/chủ phòng khám duyệt nguồn; ghi lại ai duyệt"""
    id_ = await tao_text(kb_api, "Chăm sóc sau laser")
    for role in ("cs_staff", "manager", "reception"):
        res = await kb_api.client.patch(
            f"{kb_api.base}/sources/{id_}/approval",
            json={"approved": True},
            headers=kb_api.headers(role=role),
        )
        assert res.status_code == 403, role
    res = await kb_api.client.patch(
        f"{kb_api.base}/sources/{id_}/approval",
        json={"approved": True},
        headers=kb_api.headers(role="doctor"),
    )
    assert res.status_code == 200
    assert res.json()["approved_by_clinical_owner"] is True
    assert str(
        kb_api.kb_database.scalar("SELECT approved_by FROM agent.kb_document WHERE id = :id", {"id": id_})
    ) == str(kb_api.user_id)


async def test_post_search_previews_the_hybrid_search_for_staff_default_deny_applies(kb_api: KbApi) -> None:
    """(thêm) xem trước tìm kiếm cho nhân viên; mặc định đóng vẫn áp dụng"""
    kb_api.kb_database.add_agent("tro-ly")
    id_ = await tao_text(kb_api, "Chăm sóc sau laser", "Tránh nắng và không bôi acid trong một tuần.")
    kb_api.kb_database.execute(
        "INSERT INTO agent.kb_chunk (clinic_id, source_id, ord, title, content, folded) "
        "VALUES (:c, :s, 0, '', 'Tránh nắng và không bôi acid trong một tuần.', 'Tranh nang va khong boi acid')",
        {"c": kb_api.kb_database.clinic_id, "s": id_},
    )
    body = {"query": "tránh nắng", "agent_id": "tro-ly", "limit": 5}
    res = await kb_api.client.post(f"{kb_api.base}/search", json=body, headers=kb_api.headers())
    assert res.status_code == 200
    assert res.json() == {"hits": []}, "agent chưa gán nguồn nào thì đọc được RỖNG"
    await kb_api.client.put(
        f"{kb_api.base}/agents/tro-ly/sources", json={"ids": [id_]}, headers=kb_api.headers()
    )
    res = await kb_api.client.post(f"{kb_api.base}/search", json=body, headers=kb_api.headers())
    assert [h["source_id"] for h in res.json()["hits"]] == [id_]


async def test_auth_every_kb_route_demands_a_session_even_the_routes_that_write_to_disk(
    kb_api: KbApi,
) -> None:
    """mọi route KB đều đòi đăng nhập, KỂ CẢ route ghi ra đĩa"""
    duong = [
        ("GET", "/sources"),
        ("POST", "/sources/text"),
        # I16: the ONLY route that writes a file to disk was once left out of the auth test.
        ("POST", "/sources/file"),
        ("DELETE", "/sources/x"),
        ("POST", "/sources/x/reindex"),
        ("PATCH", "/sources/x/approval"),
        ("GET", "/sources/x/chunks"),
        ("GET", "/sources/x/agents"),
        ("GET", "/agents/a/sources"),
        ("PUT", "/agents/a/sources"),
        # The REVERSE binding is a WRITE route too: leaving it out would leave open exactly what this list
        # exists to guard.
        ("PUT", "/sources/x/agents"),
        ("POST", "/search"),
    ]
    for method, path in duong:
        res = await kb_api.client.request(method, f"{kb_api.base}{path}")
        assert res.status_code == 401, f"{method} {path} không đòi đăng nhập"


async def test_auth_a_reader_cannot_write_and_a_caller_without_kb_permissions_cannot_read(
    kb_api: KbApi,
) -> None:
    """(thêm) kb.read không đủ để ghi; thiếu cả kb.read thì không đọc được"""
    doc = kb_api.headers(permissions="kb.read")
    res = await kb_api.client.post(
        f"{kb_api.base}/sources/text", json={"name": "x", "text": "y"}, headers=doc
    )
    assert res.status_code == 403
    assert (await kb_api.client.get(f"{kb_api.base}/sources", headers=doc)).status_code == 200
    khong_quyen = kb_api.headers(permissions="patient.read")
    assert (await kb_api.client.get(f"{kb_api.base}/sources", headers=khong_quyen)).status_code == 403


async def test_clinic_boundary_a_caller_of_another_clinic_sees_and_changes_nothing(kb_api: KbApi) -> None:
    """(thêm, RLS) phòng khám khác không thấy, không xóa, không duyệt được nguồn"""
    id_ = await tao_text(kb_api, "Của phòng khám A")
    khac = kb_api.headers(role="owner", clinic=kb_api.kb_database.other_clinic_id)
    assert (await kb_api.client.get(f"{kb_api.base}/sources", headers=khac)).json() == []
    assert (await kb_api.client.delete(f"{kb_api.base}/sources/{id_}", headers=khac)).status_code == 404
    res = await kb_api.client.patch(
        f"{kb_api.base}/sources/{id_}/approval", json={"approved": True}, headers=khac
    )
    assert res.status_code == 404
    assert so_nguon(kb_api) == 1
