"""Prompt text and prompt assembly for the answering agent.

Prompts are production code: they decide what a Sale reads out to a customer. Keeping
them in one module means a change to how the agent speaks is a reviewable diff here,
rather than a string edited somewhere inside the orchestration logic.

SYSTEM_INSTRUCTION_VERSION is bumped whenever the wording changes meaningfully, so an
answer in the logs can be tied back to the instructions that produced it.
"""

from dataclasses import dataclass

from backend.ai.answer_cleanup import wants_images_for_prompt
from backend.services.inventory_service import InventoryUnit

SYSTEM_INSTRUCTION_VERSION = "2026-08-15.1"

# An agent answer is up to six bullet lines; pasted in full, six of those crowd out the
# retrieved context they are supposed to sit beside. Only enough of each is kept to
# establish what was being discussed — the Sale's own questions are never truncated,
# being short already and carrying the thread of the conversation.
HISTORY_ANSWER_MAX_CHARS = 300


@dataclass(frozen=True)
class ConversationTurn:
    """One earlier turn of the current session, as short-term working memory.

    Deliberately not the ORM `Message`: the prompt layer needs only who spoke and what
    was said, and keeping it a plain value means prompt assembly can be tested without a
    database.
    """

    is_sale: bool
    content: str


def format_history(turns: list[ConversationTurn]) -> str:
    """Render earlier turns as labelled lines, oldest first."""
    lines = []
    for turn in turns:
        text = " ".join((turn.content or "").split())
        if not text:
            continue
        if not turn.is_sale and len(text) > HISTORY_ANSWER_MAX_CHARS:
            text = text[:HISTORY_ANSWER_MAX_CHARS].rstrip() + "..."
        lines.append(f"{'Sale' if turn.is_sale else 'Trợ lý'}: {text}")
    return "\n".join(lines)


def build_retrieval_query(query: str, turns: list[ConversationTurn]) -> str:
    """Expand a context-dependent follow-up into something worth embedding.

    "Còn 3PN thì sao?" carries no project, no subdivision and no topic, so on its own it
    embeds to nothing useful and retrieval retrieves nothing useful. Prepending the Sale's
    previous question puts those nouns back into the vector.

    Only the Sale's own questions are used, never the agent's answers: an answer is long
    enough to dominate the embedding and drag retrieval towards whatever it happened to
    mention rather than towards what is being asked now.
    """
    previous = [turn.content for turn in turns if turn.is_sale and turn.content and turn.content.strip()]
    if not previous:
        return query
    return f"{previous[-1].strip()}\n{query}"

# Block order is deliberate and should not be reshuffled: role -> length -> layout ->
# required content -> format -> grounding constraints. A model reading "senior
# real-estate consultant" slides easily into a sales pitch and fills in market figures
# it "knows" from pre-training, so the grounding block comes last and is phrased
# absolutely, overriding every requirement above it.
#
# The length ceiling sits near the top on purpose. An earlier revision opened with
# "answer fully, in detail, better long than incomplete" and produced walls of prose a
# Sale could not skim in front of a customer. The cap has to be read before the list of
# what must be covered, not after it.
SYSTEM_INSTRUCTION = (
    "Bạn là chuyên viên tư vấn bất động sản nhiều năm kinh nghiệm, đang brief nhanh cho đồng "
    "nghiệp trong đội sale sắp gặp khách. Họ đọc câu trả lời của bạn ngay trước mặt khách, nên "
    "phải nắm được ý trong vài giây.\n"
    "\n"
    "ĐỘ DÀI — ưu tiên hàng đầu:\n"
    "- Tối đa 6 gạch đầu dòng, mỗi dòng 1-2 câu. Câu hỏi đơn giản chỉ cần 2-3 dòng.\n"
    "- Ngắn nhưng không thiếu ý chính. Nếu phải cắt, giữ lại con số và điều kiện kèm theo, "
    "bỏ phần diễn giải.\n"
    "- Không lặp lại câu hỏi, không mở bài, không tóm tắt lại ở cuối, không khuyên chung chung "
    "kiểu 'nên tư vấn kỹ cho khách'.\n"
    "\n"
    "TRÌNH BÀY — luôn dùng gạch đầu dòng:\n"
    "- Mỗi ý một dòng, bắt đầu bằng '- '. Không viết đoạn văn xuôi dài.\n"
    "- Dòng đầu tiên chứa con số hoặc thông tin chính mà Sale hỏi.\n"
    "- Mỗi dòng nêu trọn một ý, không cắt ngang câu sang dòng khác.\n"
    "- Không lồng gạch đầu dòng nhiều cấp.\n"
    "\n"
    "NỘI DUNG BẮT BUỘC — dù ngắn vẫn phải có, khi ngữ cảnh cung cấp:\n"
    "- Con số chính (giá, diện tích, tiến độ) và nó áp dụng cho loại căn / phân khu / tòa nào.\n"
    "- Điều kiện đi kèm: đã gồm hay chưa gồm VAT, tính trên diện tích nào, điều kiện hưởng "
    "chiết khấu, mốc thời gian hết hạn chính sách.\n"
    "- Cảnh báo ngắn nếu có điểm Sale dễ tư vấn sai (chi phí khách không lường trước, tài liệu "
    "mâu thuẫn, chính sách sắp hết hiệu lực).\n"
    "- Phần nào ngữ cảnh chưa có dữ liệu thì nói thẳng trong một dòng.\n"
    "- Chỉ nêu thông tin liên quan trực tiếp tới câu hỏi. Không kể thêm tiện ích, chính sách hay "
    "loại căn khác mà Sale không hỏi.\n"
    "\n"
    "GIỌNG VĂN:\n"
    "- Như nói với đồng nghiệp có nghề: thành câu, tự nhiên, không máy móc.\n"
    "- Thuật ngữ đúng chuẩn ngành: căn 2PN, diện tích thông thủy, bàn giao thô/hoàn thiện, "
    "chiết khấu, ân hạn nợ gốc, sở hữu lâu dài, tiến độ thanh toán.\n"
    "- Số liệu kèm đơn vị (m², tỷ đồng, triệu đồng/m², %).\n"
    "- Giao diện đã hiện danh sách tài liệu nguồn ngay dưới câu trả lời, nên KHÔNG viết tên tài "
    "liệu, số trang hay số thứ tự khối ngữ cảnh vào trong câu trả lời. Tuyệt đối không mở đầu "
    "dòng bằng [1], [2], và không viết '(theo trang 3)' hay '(Tồn kho real-time)'.\n"
    "- Không lặp lại thông tin đã nêu ở dòng trước. Nếu cả nhóm cùng một trạng thái hay một "
    "loại căn, nói một lần ở dòng mở đầu rồi thôi.\n"
    "- Trạng thái tồn kho viết bằng tiếng Việt (còn trống, đã đặt chỗ, đã bán), không để nguyên "
    "mã tiếng Anh của API.\n"
    "\n"
    "ĐỊNH DẠNG — giao diện hiển thị văn bản thuần, KHÔNG render Markdown:\n"
    "- Tuyệt đối không dùng ký tự Markdown: không **in đậm**, không *nghiêng*, không ###, "
    "không bảng, không khối mã. Chúng sẽ hiện nguyên dấu sao trên màn hình và trông rất lỗi.\n"
    "- Cần nhấn mạnh thì đặt thông tin đó ở đầu dòng, không tô đậm.\n"
    "- Không chào hỏi, không văn quảng cáo sáo rỗng, không emoji.\n"
    "\n"
    "RÀNG BUỘC BẮT BUỘC — quan trọng hơn mọi yêu cầu về độ dài và phong cách ở trên:\n"
    "- CHỈ dùng thông tin có trong NGỮ CẢNH được cung cấp. Kiến thức bên ngoài về thị trường, "
    "chủ đầu tư hay dự án khác đều KHÔNG được dùng, kể cả khi bạn chắc chắn.\n"
    "- Tuyệt đối không suy diễn, không nội suy, không làm tròn hay ước lượng giá, diện tích, "
    "tiến độ, chính sách khi ngữ cảnh không ghi rõ. Không tự tính đơn giá/m² hay tổng giá nếu "
    "ngữ cảnh không cho đủ dữ kiện.\n"
    "- Không hứa hẹn, không cam kết thay chủ đầu tư (giữ chỗ, chắc chắn tăng giá, cam kết lợi nhuận...).\n"
    "- Nếu ngữ cảnh thiếu thông tin, nói thẳng trong một dòng là chưa có dữ liệu và đề nghị kiểm "
    "tra với Admin — không lấp đầy bằng phỏng đoán, cũng không viết dài ra để che chỗ thiếu.\n"
    "- Khi ngữ cảnh có nhiều số liệu mâu thuẫn, nêu rõ sự khác biệt kèm nguồn của từng tài liệu, "
    "thay vì tự chọn một số."
)


def build_prompt(
    query: str,
    docs: list[dict],
    units: list[InventoryUnit],
    needs_inventory: bool,
    inventory_failed: bool,
    images: list[dict] | None = None,
    history: list[ConversationTurn] | None = None,
    profile: str = "",
) -> str:
    sections = []

    if profile.strip():
        # Long-term memory: who this person is, not what is true about the project.
        # Framed even more strictly than the history block below, because a remembered
        # budget looks deceptively like a fact — it is a hint for *framing* the answer,
        # never a figure to quote, and must never narrow what gets answered.
        sections.append(
            f"GHI NHỚ VỀ NGƯỜI HỎI (từ các phiên trước, chỉ để tham khảo):\n{profile}\n"
            "Đây là sở thích đã ghi nhận, KHÔNG phải dữ liệu dự án. Tuyệt đối không dùng "
            "làm số liệu trả lời và không tự suy ra nhu cầu hiện tại từ nó. Luôn trả lời "
            "đúng câu hỏi được hỏi; nếu câu hỏi mâu thuẫn với ghi nhớ, câu hỏi thắng."
        )

    if history:
        rendered = format_history(history)
        if rendered:
            # Placed before the question so the model reads the thread first, and framed
            # strictly as reference. Earlier turns are conversational context only — they
            # are NOT grounding. The figures in them came from documents retrieved for a
            # different question, and letting the model answer out of its own previous
            # answer is exactly how a stale price survives into a new turn.
            sections.append(
                f"LỊCH SỬ HỘI THOẠI (cũ nhất trước, chỉ để hiểu ngữ cảnh):\n{rendered}\n"
                "Lịch sử chỉ dùng để hiểu Sale đang nói về dự án / loại căn nào. TUYỆT ĐỐI "
                "không lấy số liệu từ lịch sử để trả lời — mọi con số phải lấy từ NGỮ CẢNH "
                "bên dưới. Nếu câu hỏi mới cần số liệu mà ngữ cảnh không có, nói thẳng là "
                "chưa có dữ liệu."
            )

    sections.append(f"CÂU HỎI CỦA SALE:\n{query}")

    if docs:
        context = "\n\n".join(_format_doc(index, doc) for index, doc in enumerate(docs, start=1))
        sections.append(f"NGỮ CẢNH TỪ TÀI LIỆU DỰ ÁN:\n{context}")

    if needs_inventory and not inventory_failed:
        sections.append(f"TỒN KHO REAL-TIME:\n{_format_units(units)}")

    sections.append(
        "Trả lời câu hỏi trên với tư cách chuyên viên tư vấn dự án, ngắn gọn và đúng trọng tâm "
        "như đang brief cho đồng nghiệp sắp gặp khách. Văn bản thuần, không dùng ký tự Markdown "
        "nào (không dấu sao, không thăng).\n"
        "- Trình bày bằng gạch đầu dòng, mỗi dòng bắt đầu bằng '- '. Tối đa 6 dòng.\n"
        "- Dòng đầu tiên trả lời thẳng điều Sale hỏi, kèm con số chính.\n"
        "- Bám đúng loại căn / phân khu / tòa mà câu hỏi nhắc tới, đừng trả lời chung chung cho "
        "cả dự án khi Sale đang hỏi một loại căn cụ thể.\n"
        "- Kèm điều kiện áp dụng của con số (VAT, diện tích tính theo, mốc thời gian) ngay trong "
        "dòng nêu con số đó, thay vì tách thành dòng riêng.\n"
        "- Không viết tên tài liệu, số trang hay số thứ tự khối ngữ cảnh ([1], [2]) vào câu trả "
        "lời — giao diện đã hiện phần nguồn riêng bên dưới.\n"
        "- Nếu ngữ cảnh chưa có dữ liệu cho phần nào, nói thẳng trong một dòng thay vì suy đoán."
    )

    if images:
        # The tool has already run, so this states a fact rather than a promise. Without it
        # the model reads "no images in the context" off its own prompt and tells the Sale
        # to ask Admin for pictures — printed directly above a strip of those pictures.
        project_name = images[0].get("project_name") or "dự án"
        sections.append(
            f"ẢNH ĐÃ ĐÍNH KÈM: {len(images)} ảnh {project_name} ĐANG hiển thị trên màn hình của "
            "Sale, ngay dưới câu trả lời này. CẤM tuyệt đối mọi câu phủ nhận điều đó — không viết "
            "'không có hình ảnh', 'không có tệp ảnh', 'tài liệu không chứa ảnh', 'không hiển thị "
            "được ảnh', và không bảo Sale hỏi Admin xin ảnh. Không mô tả từng ảnh. Phần chữ chỉ "
            "tóm tắt 2-3 dòng về hạng mục được hỏi dựa trên ngữ cảnh."
        )
    elif wants_images_for_prompt(query):
        sections.append(
            "ẢNH: catalogue không có ảnh nào khớp yêu cầu này. Nói ngắn gọn trong một dòng là "
            "chưa có ảnh cho hạng mục được hỏi."
        )

    if needs_inventory and inventory_failed:
        sections.append(
            "LIVE INVENTORY STATUS: unavailable. Do not infer stock from project documents; "
            "state that live inventory could not be checked."
        )

    return "\n\n".join(sections)


def _format_doc(index: int, doc: dict) -> str:
    """One context block: index + document title + page so the LLM can cite down to the page."""
    title = doc.get("title") or "Tài liệu"
    page = doc.get("page")
    header = f"[{index}] {title}" + (f" (trang {page})" if page else "")
    return f"{header}\n{doc.get('content') or ''}"


def _format_units(units: list[InventoryUnit]) -> str:
    if not units:
        return "Hiện không còn căn nào khớp với yêu cầu."

    return "\n".join(
        f"- {unit.unit_code} | loại {unit.unit_type or 'không rõ'} | "
        f"giá {f'{unit.price:,.0f} VNĐ' if unit.price is not None else 'chưa có'} | {unit.status}"
        for unit in units
    )


def format_unit_for_verifier(unit: InventoryUnit) -> str:
    """Give the verifier the same live facts that were supplied to the LLM."""
    return (
        f"Live inventory: {unit.unit_code}; type {unit.unit_type or 'unknown'}; "
        f"price {unit.price if unit.price is not None else 'unknown'}; status {unit.status}."
    )
