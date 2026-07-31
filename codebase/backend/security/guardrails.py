"""Deterministic routing, query shaping and data guardrails."""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata

from ..utils.text_utils import remove_vietnamese_tone, tokenize


RESTRICTED_RE = re.compile(
    r"(số điện thoại|email|gmail|zalo|facebook|telegram|mssv|cccd|cmnd|địa chỉ|"
    r"tên thật|danh tính|user_id|conversation_id|message_id|raw|dump|nguyên file|"
    r"nguyên văn|toàn bộ transcript|toàn bộ chatlog|xuất data|xuất dữ liệu|"
    r"cho.*đáp án|đáp án.*(?:quiz|bài kiểm tra|exam|test|self-check)|làm hộ|viết hộ|nộp hộ|mã pin kahoot|mã quiz)",
    re.IGNORECASE,
)
PII_INPUT_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.-]+|"
    r"(?<!\d)(?:\+?84|0)(?:\s|\.|-)?(?:3|5|7|8|9)(?:\d(?:\s|\.|-)?){8}(?!\d)",
    re.IGNORECASE,
)
CASUAL_OUT_OF_SCOPE_RE = re.compile(
    r"(cách nấu|nấu ăn|món ăn nhanh|thời tiết|bóng đá|đặt vé|mua hàng|xem phim|nghe nhạc|du lịch|"
    r"trồng hoa|trồng cây|chăm cây|hoa lan|orchid|gardening|grow orchids|"
    r"chăm sóc (?:chó|mèo)|chó con|mèo con|thú cưng|pet care|puppy|kitten|"
    r"san hô|coral reef|quantum|photon|động cơ|engine|carburetor|motorcycle|"
    r"làm bánh|công thức nấu|sourdough|fertilizer|hydroponic|"
    r"học phí|deadline|hạn nộp|link nộp|điểm danh|phòng học|mã lớp)",
    re.IGNORECASE,
)
ADMIN_OUT_OF_SCOPE_RE = re.compile(
    r"(deadline|hạn nộp|link nộp|nộp bài ở đâu|nộp.*mấy giờ|điểm danh|"
    r"nộp.*muộn|học bù|lịch học|lịch thi|tuần sau.*(?:ngày|giờ)|"
    r"phòng học|phòng nào|lớp.*phòng|mã lớp|học phí|chứng chỉ|certificate|"
    r"danh sách nhóm|ai.*chấm bài|điểm tối đa|mật khẩu wifi|wifi.*lớp)",
    re.IGNORECASE,
)
AMBIGUOUS_CONTEXT_RE = re.compile(
    r"(cái này|cái đó|cái kia|này là gì|đó là gì|phần đó|phần này|đoạn đó|đoạn này|"
    r"phần trên|phần dưới|đoạn bôi đen|bôi đen|selected text|"
    r"ý thứ (?:nhất|hai|ba)|bước đó|vừa rồi|vừa nói|"
    r"giải thích thêm\s*(?:đi)?\s*$|nó hoạt động.*(?:sao|thế nào)|"
    r"tóm tắt\s*(?:phần|đoạn|cái|nội dung)?\s*(?:đó|này|kia)?\s*$)",
    re.IGNORECASE,
)
NORMALIZED_AMBIGUOUS_CONTEXT_RE = re.compile(
    r"(cai nay|cai do|cai kia|phan do|phan nay|doan do|doan nay|"
    r"phan tren|phan duoi|boi den|y thu (?:nhat|hai|ba)|buoc do|vua roi|vua noi|"
    r"giai thich them\s*(?:di)?\s*$|no hoat dong.*(?:sao|the nao)|"
    r"tom tat\s*(?:phan|doan|cai|noi dung)?\s*(?:do|nay|kia)?\s*$)",
    re.IGNORECASE,
)
NORMALIZED_ADMIN_OUT_OF_SCOPE_TERMS = (
    "hoc phi",
    "deadline",
    "han nop",
    "link nop",
    "nop bai",
    "diem danh",
    "phong hoc",
    "phong nao",
    "ma lop",
    "chung chi",
    "certificate",
    "hoc bu",
    "lich hoc",
    "lich thi",
    "nop muon",
    "danh sach nhom",
    "diem toi da",
    "mat khau wifi",
)
NORMALIZED_CASUAL_OUT_OF_SCOPE_TERMS = (
    "cach nau",
    "nau an",
    "mon an",
    "thoi tiet",
    "bong da",
    "dat ve",
    "mua hang",
    "xem phim",
    "nghe nhac",
    "du lich",
    "trong hoa",
    "trong cay",
    "cham cay",
    "hoa lan",
    "orchid",
    "gardening",
    "grow orchids",
    "cham soc cho",
    "cho con",
    "meo con",
    "thu cung",
    "pet care",
    "puppy",
    "kitten",
    "san ho",
    "coral reef",
    "quantum",
    "photon",
    "dong co",
    "engine",
    "carburetor",
    "motorcycle",
    "lam banh",
    "sourdough",
    "fertilizer",
    "hydroponic",
)
CURRENT_SLIDE_CONTEXT_RE = re.compile(
    r"(slide này|trang này|trang hiện tại|slide hiện tại|trang đang xem|slide đang xem|"
    r"phần này|đoạn này|phần trên|phần dưới|tóm tắt\s*(?:trang|slide|phần|đoạn|nội dung)?\s*(?:này|hiện tại)?\s*$)",
    re.IGNORECASE,
)
CONTEXTUAL_FOLLOWUP_RE = re.compile(
    r"\b(?:no|cai do|phan do|doan do|con|tiep theo|khac gi|so voi|vay con|this|that|it|what about|how about|next|different)\b",
    re.IGNORECASE,
)
MIN_SLIDE_SCORE = 8
GENERIC_RETRIEVAL_TERMS = {
    "ai",
    "model",
    "product",
    "prompt",
    "workflow",
    "data",
    "system",
    "nguon",
    "noi",
    "dung",
    "lam",
    "phan",
    "context",
    "source",
    "value",
    "cost",
    "outcome",
    "impact",
    "effort",
    "baseline",
    "scope",
    "problem",
    "use",
    "case",
}
COURSE_QUERY_EXPANSIONS = {
    "phat bieu bai toan": "problem statement",
    "xac dinh van de": "problem statement define problem scope",
    "tim dung van de": "discover define problem statement double diamond",
    "mo rong goc nhin": "discover divergence observation interview survey",
    "thu hep van de": "define convergence problem statement",
    "kiem chung gia thuyet": "validate hypothesis prototype experiment evaluation",
    "luong hoa tac dong": "measurement baseline metric impact outcome",
    "tac nhan ai": "ai agent workflow autonomy tools",
    "quy trinh tac nhan": "ai agent workflow tools planning reflection",
    "truy xuat nguon": "rag retrieval grounding citation source",
    "context": "context window context rot attention prompt important instruction lost middle",
    "quick win": "impact effort priority low effort high impact use case",
    "impact effort": "quick win priority low effort high impact use case",
    "roi": "baseline measurement impact value cost outcome",
    "rag": "rag retrieval augmented generation grounding citation source context hallucination",
    "citation": "rag retrieval augmented generation grounding citation source context hallucination",
    "mvp": "scope problem prototype validate evaluation baseline go not yet",
    "poc": "scope problem prototype validate evaluation baseline go not yet",
    "khi nao khong nen dua ai vao san pham": "scope risk boundary not yet augment automate controls",
    "khong nen dua ai": "scope risk boundary not yet augment automate controls",
    "dua ai vao san pham": "scope problem risk boundary automate augment controls",
    "khi nao nen dung ai": "automate augment workflow boundary controls",
}
COURSE_CANONICAL_TERMS = {
    "agent",
    "attention",
    "autonomy",
    "automate",
    "augmentation",
    "baseline",
    "citation",
    "convergence",
    "context",
    "decision",
    "define",
    "deliver",
    "develop",
    "diamond",
    "discriminative",
    "discover",
    "divergence",
    "effort",
    "evaluation",
    "experiment",
    "feasibility",
    "generative",
    "generation",
    "grounding",
    "hallucination",
    "hypothesis",
    "impact",
    "interview",
    "measurement",
    "metric",
    "objective",
    "observation",
    "outcome",
    "planning",
    "problem",
    "prompt",
    "prototype",
    "recall",
    "reflection",
    "retrieval",
    "reward",
    "scope",
    "statement",
    "survey",
    "transcript",
    "transformer",
    "validate",
    "viability",
    "workflow",
}
EXACT_SOURCE_ANCHOR_TERMS = {
    "roi",
    "rag",
    "citation",
    "mvp",
    "poc",
    "agent",
    "workflow",
    "context",
    "attention",
    "prompt",
    "transformer",
}
DIRECT_TOPIC_TERMS = {
    "roi",
    "rag",
    "citation",
    "hallucination",
    "mvp",
    "poc",
    "agent",
    "workflow",
    "context",
    "attention",
    "prompt",
    "transformer",
}
MISSING_SOURCE_RE = re.compile(
    r"\b(?:slide|trang)\s*\d{3,}\b",
    re.IGNORECASE,
)
LEARNING_CONTEXT_RE = re.compile(
    r"\b(?:thầy|cô|slide|trang|bài|lesson|lecture|transcript|vlearn|học|giảng|case|ví dụ|use case)\b",
    re.IGNORECASE,
)
COURSE_TOPIC_RE = re.compile(
    r"(ai agent|agent|workflow|rag|citation|grounding|hallucination|mvp|poc|llm|"
    r"transformer|attention|prompt|context|use case|product|scope|pitch|"
    r"quick win|impact|effort|baseline|measurement|prototype|automate|augment|"
    r"tim dung van de|xac dinh van de|phat bieu bai toan|mo rong goc nhin|"
    r"thu hep van de|kiem chung gia thuyet|luong hoa tac dong|tac nhan ai|"
    r"(?:khong|chua)\s+(?:nen|can)\s+(?:dua|dung|su dung)\s+ai|"
    r"(?:dua|dung|su dung)\s+ai\s+(?:vao|cho)|ai\s+(?:vao|trong)\s+(?:san pham|workflow))",
    re.IGNORECASE,
)

def fallback_classify(user_input: str) -> dict:
    text = user_input.strip()
    lowered = text.lower()
    guardrail = deterministic_guardrail(text)
    if guardrail:
        return guardrail

    if len(text) < 8 or re.fullmatch(r"(as+d+s?|hỏi gì|không nhớ|cái đó.*)", lowered):
        label = "CLARIFY"
        query = ""
        question = "Bạn muốn tìm phần liên quan đến use case, workflow hay RAG/citation?"
    elif re.search(r"(slide này|trang này|đoạn này|phần này|bôi đen|đoạn được chọn)", lowered):
        label = "CLARIFY"
        query = ""
        question = "Bạn có thể nhập thêm tiêu đề slide hoặc từ khóa chính của đoạn đó không?"
    elif re.search(r"\b(?:slide|trang)\s*\d{3,}\b", remove_vietnamese_tone(lowered)):
        label = "OUT_OF_SCOPE"
        query = ""
        question = ""
    else:
        label = "FOUND_CANDIDATE"
        query = make_simple_query(text)
        question = ""

    return {
        "label": label,
        "query": query,
        "clarifying_question": question,
        "source": "fallback",
    }


def deterministic_guardrail(value: str) -> dict | None:
    lowered = value.strip().lower()
    normalized = remove_vietnamese_tone(lowered)

    if RESTRICTED_RE.search(value) or PII_INPUT_RE.search(value):
        return {
            "label": "RESTRICTED",
            "query": "",
            "clarifying_question": "",
            "source": "local_guardrail",
        }

    if MISSING_SOURCE_RE.search(normalized):
        return {
            "label": "OUT_OF_SCOPE",
            "query": "",
            "clarifying_question": "",
            "source": "local_guardrail",
        }

    if (
        ADMIN_OUT_OF_SCOPE_RE.search(value)
        or any(term in normalized for term in NORMALIZED_ADMIN_OUT_OF_SCOPE_TERMS)
        or is_likely_out_of_scope(value)
    ):
        return {
            "label": "OUT_OF_SCOPE",
            "query": "",
            "clarifying_question": "",
            "source": "local_guardrail",
        }

    if len(value.strip()) < 8 or re.fullmatch(r"(as+d+s?|hỏi gì|không nhớ|thầy nói gì nhỉ)", lowered):
        return {
            "label": "CLARIFY",
            "query": "",
            "clarifying_question": "Bạn muốn tìm phần liên quan đến use case, workflow hay RAG/citation?",
            "source": "local_clarify",
        }

    if AMBIGUOUS_CONTEXT_RE.search(value) or NORMALIZED_AMBIGUOUS_CONTEXT_RE.search(normalized):
        return {
            "label": "CLARIFY",
            "query": "",
            "clarifying_question": "Bạn muốn tìm phần liên quan đến chủ đề nào, slide nào, hoặc đoạn được chọn nào?",
            "source": "local_clarify",
        }

    return None


def is_likely_out_of_scope(value: str) -> bool:
    normalized = remove_vietnamese_tone(value.lower())
    casual = CASUAL_OUT_OF_SCOPE_RE.search(value) or any(
        term in normalized for term in NORMALIZED_CASUAL_OUT_OF_SCOPE_TERMS
    )
    return bool(casual and not LEARNING_CONTEXT_RE.search(value))


def is_course_topic(value: str) -> bool:
    normalized = remove_vietnamese_tone(value.lower())
    return bool(
        COURSE_TOPIC_RE.search(normalized)
        or re.search(r"\b(?:roi|return on investment)\b", value, re.IGNORECASE)
    )


def expand_course_query(user_input: str, query: str) -> str:
    """Add stable course vocabulary when an intent model returns a sparse query."""
    normalized_input = remove_vietnamese_tone(user_input.lower())
    tokens = tokenize(query)
    trigger_text = f"{normalized_input} {' '.join(tokens)}"
    for trigger, expansion in COURSE_QUERY_EXPANSIONS.items():
        if trigger == "roi" and not re.search(r"\b(?:roi|return on investment)\b", user_input, re.IGNORECASE):
            continue
        if trigger in trigger_text:
            tokens.extend(tokenize(expansion))

    return " ".join(dict.fromkeys(tokens))


def correct_course_term(token: str) -> str:
    """Correct a near-miss only when it safely matches controlled course vocabulary."""
    if token in COURSE_CANONICAL_TERMS or len(token) < 5:
        return token

    matches = []
    for candidate in COURSE_CANONICAL_TERMS:
        if token[0] != candidate[0] or abs(len(token) - len(candidate)) > 2:
            continue
        similarity = SequenceMatcher(None, token, candidate).ratio()
        one_edit = len(token) == len(candidate) and sum(
            left != right for left, right in zip(token, candidate)
        ) == 1
        if similarity >= 0.82 or one_edit:
            matches.append((similarity, candidate))
    matches.sort(reverse=True)
    if not matches:
        return token
    if len(matches) > 1 and matches[0][0] - matches[1][0] < 0.04:
        return token
    return matches[0][1]


def make_simple_query(value: str) -> str:
    normalized = remove_vietnamese_tone(value.lower())
    tokens = [
        correct_course_term(token)
        for token in re.findall(r"[a-z0-9]+", normalized)
    ]
    stopwords = {
        "ban",
        "minh",
        "toi",
        "em",
        "anh",
        "chi",
        "thay",
        "co",
        "noi",
        "ve",
        "voi",
        "dau",
        "ay",
        "la",
        "gi",
        "nao",
        "phan",
        "slide",
        "trang",
        "tim",
        "cho",
        "hoi",
        "muon",
        "nho",
        "mang",
        "mot",
        "cai",
        "nay",
        "kia",
        "nhi",
        "vay",
        "nam",
        "trong",
        "duoc",
        "khong",
        "can",
        "hay",
        "theo",
        "khi",
        "nao",
        "de",
        "phai",
        "tinh",
        "kieu",
        "sai",
        "cach",
        "nhu",
        "vao",
        "san",
        "pham",
        "bai",
        "cuoi",
        "rui",
        "ro",
        "thang",
        "hom",
        "nay",
        "sao",
        "nhin",
        "gon",
        "hon",
        "bo",
        "the",
        "thi",
        "neu",
        "khac",
        "nhau",
        "nen",
        "dua",
        "chon",
    }
    kept = [token for token in tokens if len(token) > 2 and token not in stopwords]
    query = " ".join(kept[:8])
    if "retrieval augmented generation" in query:
        query = re.sub(r"\bretrieval augmented generation\b", "rag", query)
    if "return investment" in query and "roi" not in query:
        query = f"roi {query}"
    return query


def is_current_slide_request(user_input: str) -> bool:
    normalized = remove_vietnamese_tone(user_input.strip().lower())
    return bool(
        CURRENT_SLIDE_CONTEXT_RE.search(user_input.strip().lower())
        or re.search(r"\b(?:this|current)\s+(?:slide|page|section)\b", normalized)
        or re.search(
            r"(slide nay|trang nay|trang hien tai|slide hien tai|trang dang xem|slide dang xem|"
            r"phan nay|doan nay|phan tren|phan duoi|tom tat\s*(?:trang|slide|phan|doan|noi dung)?\s*(?:nay|hien tai)?\s*$)",
            normalized,
        )
    )


def is_locate_slide_request(user_input: str) -> bool:
    """Return True only when the user asks where a course topic appears."""
    normalized = remove_vietnamese_tone(user_input.strip().lower())
    return bool(
        re.search(
            r"(slide nao|trang nao|o dau|nam o dau|tim (?:slide|trang|phan)|"
            r"(?:which|what) (?:slide|page)|where (?:is|does)|find (?:the )?(?:slide|page))",
            normalized,
        )
    )


def is_contextual_followup(user_input: str) -> bool:
    return bool(CONTEXTUAL_FOLLOWUP_RE.search(remove_vietnamese_tone(user_input.lower())))


def exact_source_anchor_terms(value: str) -> set[str]:
    """Find explicit ASCII course terms without folding Vietnamese diacritics.

    This prevents acronyms such as ROI from matching ordinary Vietnamese words
    like "rồi" or "rơi" after tone removal.
    """
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    return {
        term
        for term in EXACT_SOURCE_ANCHOR_TERMS
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized)
    }
