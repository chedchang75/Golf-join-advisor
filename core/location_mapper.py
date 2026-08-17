"""
[core/location_mapper.py]
전국 주요 골프장 정식 명칭 및 지명 힌트 매핑 유틸리티
지명 힌트가 없는 모호한 구장은 임의 지역을 할당하지 않고 빈 문자열("")을 반환합니다.
"""

import re
from typing import Dict, Optional

# 전국 대표 고유 골프장 (지역이 명확한 단일 구장)
UNIQUE_GOLF_COURSE_REGION_MAP: Dict[str, str] = {
    # 경기도
    "아일랜드CC": "경기 안산",
    "솔모로CC": "경기 여주",
    "자유CC": "경기 여주",
    "세라지오CC": "경기 여주",
    "금강CC": "경기 여주",
    "루트52CC": "경기 여주",
    "페럼CC": "경기 여주",
    "플라자CC용인": "경기 용인",
    "골드CC": "경기 용인",
    "코리아CC": "경기 용인",
    "태광CC": "경기 용인",
    "한성CC": "경기 용인",
    "레이크사이드CC": "경기 용인",
    "신원CC": "경기 용인",
    "화성상록GC": "경기 화성",
    "리베라CC": "경기 화성",
    "기흥CC": "경기 화성",
    "안성베네스트GC": "경기 안성",
    "마에스트로CC": "경기 안성",
    "안성Q": "경기 안성",
    "포천힐스CC": "경기 포천",
    "몽베르CC": "경기 포천",
    "서원밸리CC": "경기 파주",
    "서원힐스CC": "경기 파주",

    # 강원도
    "센추리21CC": "강원 원주",
    "오크밸리CC": "강원 원주",
    "라데나GC": "강원 춘천",
    "엘리시안강촌": "강원 춘천",
    "로드힐스CC": "강원 춘천",
    "클럽모우CC": "강원 홍천",
    "샤인데일CC": "강원 홍천",

    # 충청도
    "로얄포레CC": "충북 충주",
    "임페리얼코걸프": "충북 충주",
    "킹스데일GC": "충북 충주",
    "대영베이스CC": "충북 충주",
    "세종에머슨CC": "세종",
    "천안상록GC": "충남 천안",
    "골든베이CC": "충남 태안",
    "롯데스카이힐부여CC": "충남 부여",
    "부여롯데스카이": "충남 부여",
    "클린밸리CC": "충북 보은",
    "클린밸리": "충북 보은",
    "백제CC": "충남 부여",
    "아리스타CC": "충남 논산",
    "아리스타": "충남 논산",

    # 전라도 & 광주
    "장수CC": "전북 장수",
    "고창CC": "전북 고창",
    "파인비치GL": "전남 해남",
    "해남파인비치": "전남 해남",
    "승주CC": "전남 순천",
    "파인힐스CC": "전남 순천",
    "보성CC": "전남 보성",
    "석정힐CC": "전북 고창",
    "석정힐고창": "전북 고창",
    "군산CC": "전북 군산",
    "어등산CC": "광주 광산",
    "웅포CC": "전북 익산",
    "태인CC": "전북 정읍",
    "화순엘리체CC": "전남 화순",
    "해피니스CC": "전남 나주",
    "전주샹그릴라CC": "전북 임실",
    "골프존카운티순천": "전남 순천",
    "순천골프존": "전남 순천",
    "스파힐스CC": "전북 김제",
    "무등산CC": "전남 화순",
    "JNJCC": "전남 장흥",
    "장흥JNJ": "전남 장흥",
    "골프존카운티드래곤": "전북 남원",
    "드래곤골프존": "전북 남원",
    "드래곤_골프존": "전북 남원",
    "솔라시도CC": "전남 해남",
    "골프존카운티선운": "전북 고창",
    "선운골프존": "전북 고창",
    "웨스트오션CC": "전남 영광",
    "푸른솔장성CC": "전남 장성",
    "아크로CC": "전남 영암",
    "함평엘리체CC": "전남 함평",
    "포세븐금강CC": "전북 익산",
    "베르힐CC": "전남 함평",

    # 경상도 & 부산
    "경주신라CC": "경북 경주",
    "대구CC": "경북 경산",
    "가야CC": "경남 김해",
    "정산CC": "경남 김해",
    "포웰CC": "경남 김해",
    "김해명문CC": "경남 김해",
    "보라CC": "울산 울주",
    "블루원경주CC": "경북 경주",
    "밀양CC": "경남 밀양",
    "밀양컨트리클럽": "경남 밀양",
    "기장동원로얄CC": "부산 기장",
    "동부산CC": "부산 기장",
    "동래베네스트CC": "부산 금정",
    "골프존카운티감포": "경북 경주",
    "보문CC": "경북 경주",
    "베이스타즈CC": "경북 포항",
    "양산CC": "경남 양산",
    "리더스CC": "경남 밀양",
    "이지스카이CC": "대구 군위",
    "아시아드CC": "부산 기장",
    "용원CC": "경남 창원",
    "다이아몬드CC": "경남 양산",
    "해운대CC": "부산 기장",
    "스톤게이트CC": "부산 기장",
    "고령오펠GC": "경북 고령",
    "고령오펠CC": "경북 고령",
    "아델스코트CC": "경남 합천",
    "청통CC": "경북 영천",
    "거창CC": "경남 거창",
    "해내다CC": "경북 구미",
    "선산CC": "경북 구미",
    "스카이뷰CC": "경남 함양",

    # 제주도
    "블랙스톤제주": "제주 제주시",
    "엘리시안제주": "제주 제주시",
    "라온CC": "제주 제주시",
    "핀크스GC": "제주 서귀포",
}

# 지명 키워드 매핑 테이블
REGION_KEYWORDS = [
    ("경주", "경북 경주"),
    ("여주", "경기 여주"),
    ("안산", "경기 안산"),
    ("용인", "경기 용인"),
    ("화성", "경기 화성"),
    ("안성", "경기 안성"),
    ("포천", "경기 포천"),
    ("파주", "경기 파주"),
    ("원주", "강원 원주"),
    ("춘천", "강원 춘천"),
    ("홍천", "강원 홍천"),
    ("충주", "충북 충주"),
    ("천안", "충남 천안"),
    ("순천", "전남 순천"),
    ("군산", "전북 군산"),
    ("김해", "경남 김해"),
    ("제주", "제주 제주시"),
    ("서귀포", "제주 서귀포"),
]


class LocationMapper:
    """골프장 이름 및 본문 텍스트 힌트를 활용한 지능형 지역 구별 유틸리티"""
    UNIQUE_GOLF_COURSE_REGION_MAP = UNIQUE_GOLF_COURSE_REGION_MAP
    REGION_KEYWORDS = dict(REGION_KEYWORDS)

    STRICT_MATCH_ONLY: bool = True  # 유저 지침에 따라 등록 DB 목록 매칭 구장만 골프장으로 사용하는 엄격 모드

    @classmethod
    def load_user_course_db(cls):
        """유저가 제공한 492개 전국 골프장 DB(user_course_db)를 SQLite에서 동적으로 자동 로드"""
        try:
            import sqlite3
            import os
            db_path = r"c:\Vibecoding\Golf join advisor\golf_advisor.db"
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_course_db'")
                if cursor.fetchone():
                    cursor.execute("SELECT course_name, category, sub_region FROM user_course_db")
                    rows = cursor.fetchall()
                    count = 0
                    for c_name, cat, sub_reg in rows:
                        if c_name and str(c_name).strip():
                            clean_c_name = str(c_name).strip()
                            reg_str = f"{cat or ''} {sub_reg or ''}".strip()
                            cls.UNIQUE_GOLF_COURSE_REGION_MAP[clean_c_name] = reg_str
                            count += 1
                    print(f"[LocationMapper] Successfully synced {count} courses from user_course_db!")
                conn.close()
        except Exception as e:
            print(f"[LocationMapper] Note on load_user_course_db: {e}")

    @classmethod
    def register_course_db(cls, course_dict: Dict[str, str]):
        """유저 제공 엑셀/CSV 골프장 목록 DB 추가 등록 메서드"""
        for course_name, region in course_dict.items():
            clean_name = course_name.strip()
            cls.UNIQUE_GOLF_COURSE_REGION_MAP[clean_name] = region.strip()

    # 💡 하네스 정밀 별칭 키워드 사전 (밴드 약어 -> 유저 DB 492개 정식 구장 1:1 매핑)
    HARNESS_ALIAS_MAP: Dict[str, str] = {
        "통도": "통도파인이스트CC",
        "통도파인": "통도파인이스트CC",
        "4well": "포웰CC",
        "4WELL": "포웰CC",
        "4-well": "포웰CC",
        "4-WELL": "포웰CC",
        "4웰": "포웰CC",
        "포웰": "포웰CC",
        "김해명문": "포웰CC",
        "김해명문포웰": "포웰CC",
        "고령오펠": "고령오펠GC",
        "아델스코트": "아델스코트CC",
        "아델": "아델스코트CC",
        "청통": "청통CC",
        "거창": "거창CC",
        "선산": "선산CC",
        "스파힐스": "스파힐스CC",
        "드래곤": "골프존카운티드래곤",
        "드래곤골프존": "골프존카운티드래곤",
        "샹그릴라": "전주샹그릴라CC",
        "선운": "골프존카운티선운",
        "솔라시도": "솔라시도CC",
        "엘리체": "화순엘리체CC",
        "클린밸리": "클린밸리CC",
        "이지스카이": "이지스카이CC",
        "리더스": "리더스CC",
        "양산": "양산CC",
        "다이아몬드": "다이아몬드CC",
        "가야": "가야CC",
        "정산": "정산CC",
        "스카이뷰": "스카이뷰CC",
        "감포": "골프존카운티감포",
        "보문": "보문CC",
        "경주신라": "경주신라CC",
        "블루원경주": "블루원경주CC",
        "해내다": "해내다CC",
        "장수": "장수CC",
        "고창": "고창CC",
        "백제": "백제CC",
        "아리스타": "아리스타CC",
        "포세븐금강": "포세븐금강CC",
        "석정힐": "석정힐CC",
        "롯데스카이힐": "롯데스카이힐부여CC",
        "롯데스카이힐부여": "롯데스카이힐부여CC",
        "롯데스카이힐 부여": "롯데스카이힐부여CC",
        "세종에머슨": "세종에머슨CC",
        "천안상록": "천안상록GC",
        "골든베이": "골든베이CC"
    }

    @classmethod
    def normalize_course_name(cls, raw_name: Optional[str]) -> str:
        """원시 구장명을 1:1 표준 구장명으로 정규화 (하네스 별칭 사전 최우선 조회)"""
        if raw_name is None or not str(raw_name).strip():
            return "미상 구장"

        clean = str(raw_name).strip()

        # 0. 하네스 정밀 별칭 사전 최우선 매칭 (통도 -> 통도파인이스트CC, 4well -> 포웰CC 등)
        clean_lower = clean.lower()
        for alias_key, full_name in cls.HARNESS_ALIAS_MAP.items():
            if alias_key.lower() == clean_lower or alias_key.lower() in clean_lower:
                return full_name
        
        # 1. EXACT MAP 1:1 매칭 검사
        if clean in cls.UNIQUE_GOLF_COURSE_REGION_MAP:
            return clean

        # 2. 줄임말 / 변형 및 어순 반전(예: 청도 오션힐스 <-> 오션힐스 청도) 매칭 검사
        clean_tokens = set(re.findall(r'[가-힣a-zA-Z0-9]+', clean.replace("CC", "").replace("GC", "").replace("클럽", "")))
        
        best_match = None
        best_score = 0

        for known, region in cls.UNIQUE_GOLF_COURSE_REGION_MAP.items():
            stem = known.replace("CC", "").replace("GC", "").replace("클럽", "").replace("골프존카운티", "").strip()
            # 직통 완전 포함 검사
            if len(stem) >= 2 and (stem == clean or stem in clean or clean in stem):
                return known

            # 단어 토큰 어순 무관 매칭 (예: ['청도', '오션힐스'] == ['오션힐스', '청도'])
            known_tokens = set(re.findall(r'[가-힣a-zA-Z0-9]+', stem))
            if clean_tokens and known_tokens:
                intersection = clean_tokens.intersection(known_tokens)
                if len(intersection) >= 2 or (len(intersection) == 1 and intersection == clean_tokens and intersection == known_tokens):
                    score = len(intersection)
                    if score > best_score:
                        best_score = score
                        best_match = known

        if best_match:
            return best_match

        # 3. 엄격 모드(STRICT_MATCH_ONLY): 등록 DB 목록에 없으면 임의 구장 생성 없이 미상 처리
        if cls.STRICT_MATCH_ONLY:
            return "미상 구장"

        # 4. CC 접미사 보정
        if not clean.endswith("CC") and not clean.endswith("GC") and not clean.endswith("클럽") and not clean.endswith("GL"):
            clean += "CC"

        return clean

    @classmethod
    def infer_course_from_text(cls, raw_text: Optional[str], band_name: Optional[str] = "") -> str:
        """본문 및 밴드명 전체 텍스트에서 100% 미상 구장을 구원하는 라스트 가드 추론기 (Null-Safe Guard)"""
        safe_raw_text = str(raw_text or "")
        safe_band_name = str(band_name or "")
        full_text = f"{safe_band_name} {safe_raw_text}"
        
        # 1. UNIQUE MAP 매칭 검사
        for known, region in cls.UNIQUE_GOLF_COURSE_REGION_MAP.items():
            stem = known.replace("CC", "").replace("GC", "").replace("클럽", "").replace("골프존카운티", "").strip()
            if len(stem) >= 2 and (stem in full_text or known in full_text):
                return known

        # 2. 밴드명에 포함된 지명/골프장 단어 추론
        if safe_band_name:
            clean_band = safe_band_name.replace("골프", "").replace("조인", "").replace("모임", "").replace("밴드", "").strip()
            if len(clean_band) >= 2:
                for known in cls.UNIQUE_GOLF_COURSE_REGION_MAP.keys():
                    stem = known.replace("CC", "").replace("GC", "").replace("클럽", "").strip()
                    if stem in clean_band or clean_band in stem:
                        return known

        # 3. 대표 지역 지명 힌트 매칭
        region_to_default_course = {
            "김제": "스파힐스CC",
            "남원": "골프존카운티드래곤",
            "순천": "파인힐스CC",
            "해남": "솔라시도CC",
            "장흥": "JNJCC",
            "고창": "골프존카운티선운",
            "영광": "웨스트오션CC",
            "함평": "함평엘리체CC",
            "화순": "무등산CC",
            "임실": "전주샹그릴라CC",
            "밀양": "밀양CC",
            "기장": "기장동원로얄CC",
            "경주": "골프존카운티감포",
            "합천": "아델스코트CC",
            "영천": "청통CC",
            "거창": "거창CC",
            "구미": "선산CC"
        }

        for hint, course in region_to_default_course.items():
            if hint in full_text:
                return course

        # 4. 밴드명 기반 구장 부여
        if safe_band_name and len(safe_band_name.strip()) > 1:
            clean_name = safe_band_name.strip()
            if not clean_name.endswith("CC") and not clean_name.endswith("골프장"):
                clean_name += "CC"
            return clean_name

        return "골프 조인 CC"

    @classmethod
    def get_region(cls, course_name: Optional[str], raw_text: Optional[str] = "") -> str:
        """골프장 명칭 및 본문 텍스트 힌트를 조합하여 정규화된 시/도 지역 추론 (Null-Safe Guard)"""
        safe_course_name = str(course_name or "")
        safe_raw_text = str(raw_text or "")

        if not safe_course_name.strip():
            return ""

        # 1. 고정 1:1 골프장 지역 맵 사전 조회 (최우선)
        normalized_course = cls.normalize_course_name(safe_course_name)
        if not normalized_course or normalized_course == "미상 구장":
            return ""

        if normalized_course in cls.UNIQUE_GOLF_COURSE_REGION_MAP:
            return cls.UNIQUE_GOLF_COURSE_REGION_MAP[normalized_course]
        
        for key, region in cls.UNIQUE_GOLF_COURSE_REGION_MAP.items():
            stem = key.replace("CC", "").replace("GC", "").replace("클럽", "").replace("골프존카운티", "").strip()
            if len(stem) >= 2 and normalized_course and stem in normalized_course:
                return region

        # 2. 본문 텍스트 내 지명 힌트 탐색
        if raw_text:
            text = raw_text.lower()
            for region_keyword, region_name in cls.REGION_KEYWORDS.items():
                if region_keyword in text:
                    return region_name

        # 3. 광역 지명 힌트 검사 (course_name + raw_text + band_name)
        combined_text = f"{normalized_course} {raw_text}".lower()
        regions_list = [
            ("경기", "경기"), ("수원", "경기"), ("용인", "경기"), ("화성", "경기"), ("성남", "경기"),
            ("강원", "강원"), ("춘천", "강원"), ("원주", "강원"), ("강릉", "강원"),
            ("충북", "충북"), ("청주", "충북"), ("충남", "충남"), ("천안", "충남"), ("아산", "충남"),
            ("전북", "전북"), ("전주", "전북"), ("군산", "전북"), ("익산", "전북"),
            ("전남", "전남"), ("목포", "전남"), ("여수", "전남"), ("순천", "전남"), ("나주", "전남"),
            ("경북", "경북"), ("포항", "경북"), ("경주", "경북"), ("김천", "경북"), ("안동", "경북"), ("구미", "경북"), ("경산", "경북"),
            ("경남", "경남"), ("창원", "경남"), ("진주", "경남"), ("통영", "경남"), ("사천", "경남"), ("김해", "경남"), ("밀양", "경남"), ("양산", "경남"),
            ("제주", "제주"), ("서귀포", "제주"),
            ("부산", "부산"), ("울산", "울산"), ("대구", "대구"), ("광주", "광주"), ("대전", "대전"), ("세종", "세종")
        ]
        for kw, reg in regions_list:
            if kw in combined_text:
                return reg

        # 4. 밴드명 내 권역 지명 추가 검사
        if course_name and ("전라" in course_name or "전남" in course_name or "전북" in course_name):
            return "전남"
        if course_name and ("경상" in course_name or "경남" in course_name or "경북" in course_name):
            return "경남"
        if course_name and ("충청" in course_name or "충남" in course_name or "충북" in course_name):
            return "충남"

        # 5. 지명 힌트가 없으면 빈 문자열("") 반환
        return ""


def infer_course_from_text(raw_text: str, band_name: str = "") -> str:
    """모듈 레벨 직접 래퍼"""
    return LocationMapper.infer_course_from_text(raw_text, band_name)


# 💡 492개 유저 엑셀 골프장 DB 자동 로드 가동
LocationMapper.load_user_course_db()
