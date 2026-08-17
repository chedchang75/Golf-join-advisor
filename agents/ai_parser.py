import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from core.schemas import GolfJoinDetail
from core.location_mapper import LocationMapper

load_dotenv()

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.prompts import ChatPromptTemplate
    LANGCHAIN_GEMINI_AVAILABLE = True
except ImportError:
    LANGCHAIN_GEMINI_AVAILABLE = False


class TextNormalizer:
    """
    [1단계: 입력 통제 (Input Harness) - Text_Normalizer]
    비정형 밴드 게시글 노이즈 제거, 전화번호 오파싱 방어 및 정규화
    """

    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return ""

        cleaned = text
        # A. URL 제거
        cleaned = re.sub(r'https?://\S+|www\.\S+', '', cleaned)
        # B. HTML 잔여물 제거
        cleaned = re.sub(r'<[^>]+>', '', cleaned)

        return cleaned.strip()

    @staticmethod
    def mask_phone_numbers(text: str) -> str:
        """전화번호(010 1234 5678, 010.1234.5678, 010. 1234. 5678, 010-1234-5678) 마스킹"""
        pattern = r'01[016789][-\s.]*\d{3,4}[-\s.]*\d{4}'
        return re.sub(pattern, ' [전화번호] ', text)


class DateParser:
    """
    [2단계: 맥락 통제 (Context Harness) - Date_Parser]
    게시글 작성일 기준 '오늘', '내일', '8/17(월)', '24일(월)' 날짜 추론
    """

    @staticmethod
    def get_current_date_str(base_date: Optional[datetime] = None) -> str:
        if base_date is None:
            base_date = datetime.now()
        return base_date.strftime("%Y-%m-%d")

    @staticmethod
    def parse_relative_date(raw_text: str, base_date: Optional[datetime] = None) -> str:
        if base_date is None:
            base_date = datetime.now()

        today = base_date
        text = raw_text.lower()

        # 직접적인 날짜 명시 (2026년 08월 17일, 8월 17일, 8/17 등)
        match_full = re.search(r'(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})', text)
        if match_full:
            year, month, day = map(int, match_full.groups())
            return f"{year:04d}-{month:02d}-{day:02d}"

        match_md = re.search(r'(\d{1,2})[/월]\s*(\d{1,2})', text)
        if match_md:
            month, day = map(int, match_md.groups())
            year = today.year
            if month < today.month:
                year += 1
            return f"{year:04d}-{month:02d}-{day:02d}"

        # 일자만 명시된 경우 (예: '24일(월)', '16 (일)') -> 작성일 기준 현재 월 추론
        match_day_only = re.search(r'(\d{1,2})\s*일?\s*\([월화수목금토일]\)', text)
        if match_day_only:
            day = int(match_day_only.group(1))
            year = today.year
            month = today.month
            return f"{year:04d}-{month:02d}-{day:02d}"

        # 상대 일자 판단 ('오늘', '내일', '모레')
        if "오늘" in text:
            return today.strftime("%Y-%m-%d")
        elif "내일" in text:
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "모레" in text or "글피" in text:
            return (today + timedelta(days=2)).strftime("%Y-%m-%d")

        return today.strftime("%Y-%m-%d")


class AIParseAgent:
    """
    [3단계: 출력 통제 (Output Harness) - Multi-Course & Multi-Slot Exploder]
    광고성 글 자동 필터링, 전화번호 그린피 방어, 카트비 별도 요금 파싱, 다중 구장 분할 파서
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model_name = os.getenv("LLM_MODEL", "gemini-2.5-pro")
        self.llm = None

        if LANGCHAIN_GEMINI_AVAILABLE and self.api_key:
            try:
                self.llm = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    temperature=0.0,
                    google_api_key=self.api_key
                )
            except Exception as e:
                print(f"[!] ChatGoogleGenerativeAI Initialization Failed: {e}")

    def parse_post(
        self,
        raw_text: str,
        band_name: str = "밴드",
        author_nickname: str = "알수없음",
        post_url: str = "",
        post_id: str = "",
        base_date: Optional[datetime] = None,
        target_start_date: Optional[str] = None,
        target_end_date: Optional[str] = None,
        **kwargs
    ) -> List[GolfJoinDetail]:
        if base_date is None:
            base_date = datetime.now()

        # [예시 1 방어]: 패키지 1박2일 광고성 단독글 자동 제외
        if self._is_ad_or_package_post(raw_text):
            print(f"[Filter Out] Ad or 1-night-2-day package post skipped: {post_id}")
            return []

        # 다중 슬롯 및 다중 구장 분할 파싱 가동 (유저 지정 수집 날짜 선반영)
        items = self._parse_multi_slots(
            raw_text, band_name, author_nickname, post_url, post_id, base_date,
            target_start_date=target_start_date, target_end_date=target_end_date,
            **kwargs
        )
        return items

    def _is_ad_or_package_post(self, text: str) -> bool:
        """1박2일 패키지 광고글 및 단순 밴드 주소 링크 광고글 판단"""
        if "패키지 리스트" in text or "국내1박2일" in text or "1박2일" in text:
            # 티오프 시간 정보(HH:MM, 00시00분)가 없으면 광고글로 판단
            if not re.search(r'(\d{1,2})[:시]\s*(\d{2})분?', text):
                return True
        return False

    def _parse_multi_slots(
        self,
        raw_text: str,
        band_name: str = "밴드",
        author_nickname: str = "알수없음",
        post_url: str = "",
        post_id: str = "",
        base_date: Optional[datetime] = None,
        target_start_date: Optional[str] = None,
        target_end_date: Optional[str] = None,
        **kwargs
    ) -> List[GolfJoinDetail]:
        """다양한 밴드 양식(다중 구장, 다중 시간, 카트비 별도, 전화번호 방어) 정밀 파싱"""
        normalized_text = TextNormalizer.normalize(raw_text)

        # 1. 밴드/작성자 헤더 및 밴드명(band_name) 기반 기본 구장명 추론
        default_course = ""
        combined_header = f"{band_name} {author_nickname} {raw_text[:250]}".lower()

        if "밀양" in combined_header:
            default_course = "밀양CC"
        elif "기장동원" in combined_header or "동원로얄" in combined_header:
            default_course = "기장동원로얄CC"
        elif "동부산" in combined_header:
            default_course = "동부산CC"
        elif "동래베네스트" in combined_header:
            default_course = "동래베네스트CC"
        elif "양산" in combined_header:
            default_course = "양산CC"
        else:
            sorted_courses = sorted(LocationMapper.UNIQUE_GOLF_COURSE_REGION_MAP.keys(), key=lambda k: len(k.replace("CC","").replace("GC","").replace("클럽","")), reverse=True)
            for known_course in sorted_courses:
                stem = known_course.replace("CC", "").replace("GC", "").replace("클럽", "").replace("골프존카운티", "").strip()
                if len(stem) >= 2 and stem.lower() in combined_header:
                    default_course = known_course
                    break

        global_date_str = DateParser.parse_relative_date(raw_text, base_date)
        is_cart_included = bool(re.search(r'카\.?포|카트포함|카트비포함|카트포', raw_text))

        # 라인 분할 전, 한 줄에 여러 구장이 명시되어 있는 경우 라인을 구장 단위로 미리 1차 분할
        raw_lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        lines = []

        sorted_courses = sorted(LocationMapper.UNIQUE_GOLF_COURSE_REGION_MAP.keys(), key=lambda k: len(k.replace("CC","").replace("GC","").replace("클럽","")), reverse=True)
        
        for raw_line in raw_lines:
            # 한 줄에 2개 이상의 구장 명칭이 등장하는가?
            found_stems = []
            for known_course in sorted_courses:
                stem = known_course.replace("CC", "").replace("GC", "").replace("클럽", "").replace("골프존카운티", "").strip()
                if len(stem) >= 2 and stem in raw_line and stem not in found_stems:
                    found_stems.append(stem)

            if len(found_stems) >= 2:
                # 구장별 1차 split 분할
                split_pattern = r'(' + r'|'.join([re.escape(s) for s in found_stems]) + r')'
                parts = re.split(split_pattern, raw_line)
                curr_part = ""
                for idx, part in enumerate(parts):
                    if part in found_stems:
                        if curr_part.strip():
                            lines.append(curr_part.strip())
                        curr_part = part
                    else:
                        curr_part += part
                if curr_part.strip():
                    lines.append(curr_part.strip())
            else:
                lines.append(raw_line)

        current_date_for_section = global_date_str
        current_course_for_section = default_course

        slot_map: Dict[str, Dict[str, Any]] = {}
        ordered_keys: List[str] = []

        for line_idx, line in enumerate(lines, 1):
            # [운영시간, 작성일시 메타데이터, 공지 안내 줄 제외]: 예: (운영시간 08:00~18:00), 2026년 8월 16일 오전 7:52 459 읽음
            if "운영시간" in line or "문의시간" in line or "안내사항" in line or "이용방법" in line or "읽음" in line or "글 옵션" in line:
                continue

            # [예시 2 방어]: 상단 3개 이상 슬래시 구장 소개 헤더 줄은 무시
            if len(re.findall(r'/[가-힣]{2,}', line)) >= 2:
                continue

            # 구장 섹션 헤더 감지 (하네스 별칭 사전 & 어순 반전 & 유저 DB 492개 매처 연동)
            line_words = re.findall(r'[가-힣a-zA-Z0-9]+', line)
            line_has_alias = False
            for w in line_words:
                if w.lower() in [k.lower() for k in LocationMapper.HARNESS_ALIAS_MAP.keys()]:
                    course_cand = LocationMapper.normalize_course_name(w)
                    if course_cand and course_cand != "미상 구장":
                        current_course_for_section = course_cand
                        line_has_alias = True
                        break

            if not line_has_alias:
                clean_line_for_header = re.sub(r'[💚🫶🌴👍📣★⛳️#]', ' ', line).strip()
                course_cand = LocationMapper.normalize_course_name(clean_line_for_header)
                if course_cand and course_cand != "미상 구장":
                    current_course_for_section = course_cand
                else:
                    sorted_courses = sorted(LocationMapper.UNIQUE_GOLF_COURSE_REGION_MAP.keys(), key=lambda k: len(k.replace("CC","").replace("GC","").replace("클럽","")), reverse=True)
                    for known_course in sorted_courses:
                        stem = known_course.replace("CC", "").replace("GC", "").replace("클럽", "").replace("골프존카운티", "").strip()
                        if len(stem) >= 2 and (f"⛳{stem}" in line or f"#{stem}" in line or line.startswith(f"⛳{known_course}") or line.startswith(known_course) or stem in line):
                            current_course_for_section = known_course
                            break

            # 섹션별 날짜 변경 감지 (예: 📣2026년08월17일, ★8/17(월), ★8/18(화), 16 (일), 24일(월), 17/월, 8/17(월/공휴일), ▶8/18(화))
            section_date_match = re.search(
                r'(\d{4})[-년.]\s*(\d{1,2})[-월.]\s*(\d{1,2})일?|'
                r'(?:^|[▶⭕️■★📣#\s])(\d{1,2})[/월]\s*(\d{1,2})(?:일|\s*\([가-힣/]+\)|일?\s*[월화수목금토일])|'
                r'(?:^|[▶⭕️■★📣#\s])(\d{1,2})\s*일\s*\([월화수목금토일]\)|'
                r'(?:^|[▶⭕️■★📣#\s])(\d{1,2})/[월화수목금토일]', line
            )
            if section_date_match and len(line) < 40:
                g1, g2, g3 = section_date_match.group(1), section_date_match.group(2), section_date_match.group(3)
                g4, g5 = section_date_match.group(4), section_date_match.group(5)
                g6, g7 = section_date_match.group(6), section_date_match.group(7)

                if g1 and g2 and g3:
                    year = int(g1)
                    month = int(g2)
                    day = int(g3)
                elif g4 and g5:
                    year = base_date.year
                    month, day = int(g4), int(g5)
                    if month < base_date.month:
                        year += 1
                elif g6:
                    year = base_date.year
                    month = base_date.month
                    day = int(g6)
                elif g7:
                    year = base_date.year
                    month = base_date.month
                    day = int(g7)
                else:
                    year = base_date.year
                    month = base_date.month
                    day = base_date.day

                current_date_for_section = f"{year:04d}-{month:02d}-{day:02d}"

                if not re.search(r'(\d{1,2})[:시]\s*(\d{1,2})분?|(?:\s|^)(\d{2})(\d{2})(?=\s|$)|⏰\s*(\d{1,2})시\s*(\d{1,2})분?', line):
                    continue

            # [이모지 키-밸류 라벨 처리]: 예: ⭕골프장명 :클린밸리(밸리), ⭕예약일자 :8월17일, ⭕예약시분 :08시38분, ⭕카트포함 :11만원
            if "골프장" in line and ":" in line:
                val = line.split(":", 1)[1].strip()
                course_cand = LocationMapper.normalize_course_name(val)
                if course_cand and course_cand != "미상 구장":
                    current_course_for_section = course_cand
                continue

            if ("예약일자" in line or "일자" in line) and ":" in line:
                date_m = re.search(r'(\d{1,2})월\s*(\d{1,2})일', line)
                if date_m:
                    m_val, d_val = map(int, (date_m.group(1), date_m.group(2)))
                    y_val = base_date.year
                    if m_val < base_date.month:
                        y_val += 1
                    current_date_for_section = f"{y_val:04d}-{m_val:02d}-{d_val:02d}"
                continue

            # 전화번호 010 마스킹
            line_no_phone = TextNormalizer.mask_phone_numbers(line)

            # [특별 규칙]: ⛳ 또는 ⛳️ 이모지 직후의 단어 추출 (예: ⛳️거창 -> 거창CC)
            emoji_course_match = re.search(r'⛳️?\s*([가-힣]{2,8}(?:CC|GC|클럽)?)', line)
            if emoji_course_match:
                candidate_name = emoji_course_match.group(1).replace("CC", "").replace("GC", "").replace("클럽", "").strip()
                for known_course in LocationMapper.UNIQUE_GOLF_COURSE_REGION_MAP.keys():
                    stem = known_course.replace("CC", "").replace("GC", "").replace("클럽", "").replace("골프존카운티", "").strip()
                    if candidate_name in stem or stem in candidate_name:
                        current_course_for_section = known_course
                        break

            # 다중 시간 패턴 탐색 (HH:MM, HH시 MM분, 4자리 HHMM 슬래시/공백 분할 등)
            times_found: List[str] = []

            # 1. HH:MM 형태 (예: 12:00, 06:51, 6:17 등)
            t_colon = re.findall(r'(\b\d{1,2}:\d{2}\b)', line_no_phone)
            for tc in t_colon:
                p_h, p_m = map(int, tc.split(":"))
                if 0 <= p_h <= 23 and 0 <= p_m <= 59:
                    if ("오후" in line or "2부" in line or "3부" in line) and p_h < 12 and p_h not in [9, 10, 11]:
                        p_h += 12
                    times_found.append(f"{p_h:02d}:{p_m:02d}")

            # 2. 4자리 HHMM 형태 (예: 1216/1244/1305, 0604/0625 등 0500~2059 범위)
            t_4digit = re.findall(r'(?:^|[\s/])(0[5-9]\d{2}|1[0-9]\d{2}|20\d{2})(?=[\s/만천원,]|$)', line_no_phone)
            for t4 in t_4digit:
                p_h = int(t4[:2])
                p_m = int(t4[2:])
                if 0 <= p_h <= 23 and 0 <= p_m <= 59:
                    t_cand = f"{p_h:02d}:{p_m:02d}"
                    if t_cand not in times_found:
                        times_found.append(t_cand)

            # 3. N시 N분 / N시N분 / N시N티 형태 (예: 13시20분, 6시33티, 8시38분)
            t_korean = re.findall(r'(\d{1,2})시\s*(\d{1,2})?(?:분|티)?', line_no_phone)
            for tk_h, tk_m in t_korean:
                p_h = int(tk_h)
                p_m = int(tk_m) if tk_m else 0
                if 0 <= p_h <= 23 and 0 <= p_m <= 59:
                    if ("오후" in line or "2부" in line or "3부" in line) and p_h < 12 and p_h not in [9, 10, 11]:
                        p_h += 12
                    t_str = f"{p_h:02d}:{p_m:02d}"
                    if t_str not in times_found:
                        times_found.append(t_str)

            if not times_found:
                # 시간이 없으나 그린피 요금 정보가 포함된 다행(Multi-line) 보충 줄인 경우 직전 슬롯에 요금 및 조건 병합
                if ordered_keys and ("그린피" in line or "카별" in line or "대기" in line or "+" in line or "만" in line or "카트포함" in line or "카포" in line or "천원" in line):
                    fee_plus = re.search(r'(?:그린피|그)?\s*(\d{1,2}(?:\.\d)?)\s*\+\s*\d', line_no_phone)
                    sub_fee = 0
                    if fee_plus:
                        sub_fee = int(float(fee_plus.group(1)) * 10000)
                    else:
                        sub_man = re.search(r'(?:카포|카별|그린피|그)?\s*(\d{1,3}(?:\.\d+)?)\s*만', line_no_phone)
                        if sub_man:
                            sub_fee = int(float(sub_man.group(1)) * 10000)
                        else:
                            sub_chun = re.search(r'(\d{2,3})\s*천원', line_no_phone)
                            if sub_chun:
                                sub_fee = int(sub_chun.group(1)) * 1000

                    last_key = ordered_keys[-1]
                    if sub_fee > 0 and slot_map[last_key]["fee"] == 0:
                        slot_map[last_key]["fee"] = sub_fee
                    if "카트포함" in line or "카포" in line:
                        if "[카트비 포함]" not in slot_map[last_key]["conditions"]:
                            slot_map[last_key]["conditions"].append("[카트비 포함]")
                    if line.strip() not in slot_map[last_key]["conditions"]:
                        slot_map[last_key]["conditions"].append(line.strip())
                continue

            # 오늘 이전 과거 날짜는 라운드 종료로 제외
            today_str = base_date.strftime("%Y-%m-%d")
            if current_date_for_section < today_str:
                continue

            # 구장명 추출 (1순위: 라인 텍스트 내 구장명 매칭)
            line_course = current_course_for_section or default_course

            # 라인 내 직접 구장 명시 검사 (예: #무등산06:09, #스파힐스/김제06:00, 드래곤_골프존06:30, 베르힐(전남)13:03)
            for known_course in sorted_courses:
                stem = known_course.replace("CC", "").replace("GC", "").replace("클럽", "").replace("골프존카운티", "").strip()
                if len(stem) >= 2 and (f"#{stem}" in line or f"⛳{stem}" in line or line.startswith(f"#{known_course}") or stem in line):
                    line_course = known_course
                    current_course_for_section = known_course
                    break

            if not line_course:
                course_match = re.search(r'([가-힣A-Za-z0-9]+(?:CC|GC|클럽|리조트|골프장))', line)
                if course_match:
                    line_course = course_match.group(1)

            if not line_course:
                line_course = "미상 구장"

            # 요금(그린피) 정밀 추출 패턴
            fee = 0
            # 0. 수수료 분리 표현 (예: 그린피 10+1.1, 그린피 10.5+1.1, 그린피 9.1+1.1)
            fee_match_plus = re.search(r'(?:그린피|그)?\s*(\d{1,2}(?:\.\d)?)\s*\+\s*\d', line_no_phone)
            if fee_match_plus:
                fee = int(float(fee_match_plus.group(1)) * 10000)

            # 1. 만 한글 명시 표현 (13만, 12.5만, 9.1만, 카포9.5만, 그린피6.6만 등)
            if fee == 0:
                fee_match_man = re.search(r'(?:카포|카별|그린피|그)?\s*(\d{1,3}(?:\.\d+)?)\s*만', line_no_phone)
                if fee_match_man:
                    fee = int(float(fee_match_man.group(1)) * 10000)

            # 2. 천원 단위 표현 (130천원, 125천원, 140천원 등)
            if fee == 0:
                fee_match_chun = re.search(r'(\d{2,3})\s*천원', line_no_phone)
                if fee_match_chun:
                    fee = int(fee_match_chun.group(1)) * 1000

            # 3. 소수점 금액 표현 (11.1, 9.1 등)
            if fee == 0:
                fee_match_float = re.search(r'(\d{1,2}\.\d{1,2})\s*만?원?', line_no_phone)
                if fee_match_float:
                    fee = int(float(fee_match_float.group(1)) * 10000)
            
            # 4. 정수 만원 표현 (그린피9, 그린피10, 그19, 그17 등)
            if fee == 0:
                fee_match_g = re.search(r'(?:그린피|그)\s*(\d{1,2})', line_no_phone)
                if fee_match_g:
                    g_val = fee_match_g.group(1)
                    if g_val:
                        fee = int(g_val) * 10000

            # 5. 괄호 안 요금 (예: (인터넷회원 80,000원), (인터넷회원 75,000원))
            if fee == 0:
                fee_match_member = re.search(r'\((?:인터넷회원|회원가?|특가)?\s*(\d{1,3}(?:,\d{3})+|\d{4,6})\s*원?\)', line_no_phone)
                if fee_match_member:
                    fee_str = fee_match_member.group(1).replace(",", "")
                    fee = int(fee_str)

            # 6. 정식 금액 (80,000원, 75000 등)
            if fee == 0:
                fee_match_won = re.search(r'(\d{1,3}(?:,\d{3})+|\d{5,6})\s*원?', line_no_phone)
                if fee_match_won:
                    fee_str = fee_match_won.group(1).replace(",", "")
                    fee = int(fee_str)

            # 7. 본문 전체에서 요금 라인이 따로 분리된 경우 섹션 요금 수색 (예: 예시 3 🍀카트별도 : 12.5만원)
            if fee == 0:
                sec_float = re.search(r'(\d{1,2}\.\d{1,2})\s*만', raw_text)
                if sec_float:
                    fee = int(float(sec_float.group(1)) * 10000)
                else:
                    sec_man = re.search(r'(\d{1,2})\s*만', raw_text)
                    if sec_man:
                        fee = int(sec_man.group(1)) * 10000

            # 카트비 포함 / 별도 문구 감지
            is_cart_inc = bool(re.search(r'카포|카트포함|카트비포함', line_no_phone))
            is_cart_extra = bool(re.search(r'카트별도|카트비별도|카별', line_no_phone + " " + raw_text))

            # 부부 / 커플 조인 판단
            is_couple = bool(re.search(r'부부|커플|남1여1|여1남1|커플초대|커플대기|커플환영', line + " " + raw_text))
            is_nocaddie = bool(re.search(r'노캐디|셀프|노캐디구장', line)) and not bool(re.search(r'노캐디\s*(?:불가|금지|안됨)', line))

            for time_str in times_found:
                # 키 생성 (날짜 + 시간 + 구장명) - 개별 레코드로 분리보장
                slot_key = f"{current_date_for_section}_{time_str}_{line_course}"

                if slot_key not in slot_map:
                    cond_list = [line.strip()]
                    if is_cart_inc and "[카트비 포함]" not in cond_list:
                        cond_list.insert(0, "[카트비 포함]")
                    slot_map[slot_key] = {
                        "course": line_course,
                        "date": current_date_for_section,
                        "time": time_str,
                        "fee": fee,
                        "conditions": cond_list,
                        "is_nocaddie": is_nocaddie,
                        "is_couple": is_couple,
                        "is_cart_extra": is_cart_extra
                    }
                    ordered_keys.append(slot_key)
                else:
                    target_slot = slot_map[slot_key]
                    if fee > 0 and target_slot["fee"] == 0:
                        target_slot["fee"] = fee
                    if is_couple:
                        target_slot["is_couple"] = True
                    if is_nocaddie:
                        target_slot["is_nocaddie"] = True
                    if line.strip() not in target_slot["conditions"]:
                        target_slot["conditions"].append(line.strip())

        # GolfJoinDetail 객체 생성 (유저 지정 수집 날짜 필터 선반영)
        results: List[GolfJoinDetail] = []
        filtered_results: List[GolfJoinDetail] = []

        for idx, key in enumerate(ordered_keys, 1):
            slot = slot_map[key]

            cond_parts = []
            if is_cart_included:
                cond_parts.append("[카트비 포함]")
            elif slot["is_cart_extra"]:
                cond_parts.append("[카트비 별도]")

            if slot["is_couple"]:
                cond_parts.append("[부부/커플 가능]")
            
            cond_parts.extend(slot["conditions"])
            merged_condition = " / ".join(cond_parts)

            # 구장명 100% 정규화 및 미상 구장 강제 구원
            raw_course_candidate = slot["course"]
            if not raw_course_candidate or raw_course_candidate in ["미상 구장", "미상", "알수없음", ""]:
                normalized_course_name = LocationMapper.infer_course_from_text(raw_text, band_name)
            else:
                normalized_course_name = LocationMapper.normalize_course_name(raw_course_candidate)

            region = LocationMapper.get_region(normalized_course_name, raw_text)

            # 구장명 + 날짜 + 시간을 포함하여 100% 독자적 고유 Primary Key 부여
            clean_course_tag = normalized_course_name.replace(' ', '').replace('CC','').replace('GC','')
            sub_post_id = f"{post_id}-{clean_course_tag}-{slot['date']}-{slot['time'].replace(':', '')}-{idx}"

            detail = GolfJoinDetail(
                golf_course=normalized_course_name,
                region=region,
                date=slot["date"],
                time=slot["time"],
                fee=slot["fee"],
                join_condition=merged_condition[:160],
                is_no_caddie=slot["is_nocaddie"],
                is_couple_possible=slot["is_couple"],
                band_name=band_name,
                author_nickname=author_nickname,
                post_url=post_url,
                post_id=sub_post_id,
                raw_text=raw_text,
                scraped_at=base_date.strftime("%Y-%m-%d %H:%M:%S")
            )
            results.append(detail)

            # 수집 파싱 선택 추출 날짜 검사
            slot_date = slot["date"]
            if target_start_date:
                if target_end_date:
                    if target_start_date <= slot_date <= target_end_date:
                        filtered_results.append(detail)
                else:
                    if slot_date == target_start_date:
                        filtered_results.append(detail)

        # 사용자가 수집 날짜(단일/범위)를 지정한 경우 해당 날짜와 일치하는 결과만 엄격히 반환 (타 날짜 유입 원천 차단)
        if target_start_date:
            return filtered_results
        return results
