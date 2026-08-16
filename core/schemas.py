from typing import Optional
from pydantic import BaseModel, Field


class GolfJoinDetail(BaseModel):
    """LLM 정제 및 DB 저장용 골프 조인 상세 데이터 스키마"""
    golf_course: str = Field(description="골프장 정식 명칭 (예: 아일랜드CC, 신라CC, 밀양CC)")
    region: str = Field(default="", description="골프장 위치 지역 (예: 경기 안산, 경남 김해, 지명 힌트 없을 시 빈값)")
    date: str = Field(description="정규화된 날짜 (Format: YYYY-MM-DD)")
    time: str = Field(description="티오프 시간 (Format: HH:MM, 24시간제)")
    fee: int = Field(default=0, description="그린피 또는 조인 참가 비용 (숫자만 추출, 불분명 시 0)")
    join_condition: str = Field(default="", description="모집 조건, 성별 제한, 카트비 포함 여부 등 유연한 텍스트")
    is_no_caddie: bool = Field(default=False, description="노캐디 진행 여부 또는 셀프 라운드 여부")
    is_couple_possible: bool = Field(default=False, description="부부 또는 커플 조인/대기 가능 여부")

    # 출처 및 메타데이터 (크롤링 시 채워짐)
    band_name: Optional[str] = Field(default="", description="수집 대상 네이버 밴드 명칭")
    author_nickname: Optional[str] = Field(default="", description="게시글 작성자 닉네임")
    post_url: Optional[str] = Field(default="", description="상세글 고유 URL")
    post_id: Optional[str] = Field(default="", description="게시글 고유 ID")
    raw_text: Optional[str] = Field(default="", description="수집된 원시 본문 텍스트")
    scraped_at: Optional[str] = Field(default="", description="수집 수행 일시 (YYYY-MM-DD HH:MM:SS)")
