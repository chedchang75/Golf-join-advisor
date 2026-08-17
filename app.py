import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import importlib
import holidays

import core.database
import agents.ai_parser
import core.location_mapper
importlib.reload(core.database)
importlib.reload(agents.ai_parser)
importlib.reload(core.location_mapper)

from core.database import init_db, fetch_golf_joins, clear_all_joins, save_golf_join
from core.config_loader import get_target_bands
from agents.collector import SessionManager, SelectiveScraper
from agents.ai_parser import AIParseAgent
from agents.data_controller import DataControlAgent

# 대한민국 법정 공휴일 & 대체공휴일 캘린더 생성
KR_HOLIDAYS = holidays.KR(years=[2025, 2026, 2027], language="ko")

# Streamlit 페이지 기본 설정
st.set_page_config(
    page_title="골프 조인 큐레이터 (Golf Join Curator)",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS 스타일링 (달력 내 일요일 및 공휴일 빨간색 강조 포함)
st.markdown("""
<style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 800;
        color: #1E3A8A;
        margin-bottom: 0.1rem;
        letter-spacing: -0.5px;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #6B7280;
        margin-bottom: 1.2rem;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.6rem;
        font-weight: 700;
        color: #0F172A;
    }
    /* 달력 피커 내 일요일/공휴일 빨간색 표기 */
    div[data-baseweb="calendar"] button:nth-child(7n+1),
    div[data-baseweb="calendar"] [aria-label*="Sunday"] {
        color: #EF4444 !important;
        font-weight: bold !important;
    }
    .holiday-badge {
        display: inline-block;
        background-color: #FEE2E2;
        color: #DC2626;
        border: 1px solid #FCA5A5;
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 12px;
        font-weight: bold;
        margin: 2px;
    }
    /* 사이드바 초밀착 컴팩트 레이아웃 최적화 */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.3rem !important;
    }
    [data-testid="stSidebar"] div[data-testid="stCheckbox"] {
        padding-top: 0px !important;
        padding-bottom: 0px !important;
        margin-top: -4px !important;
        margin-bottom: -4px !important;
    }
    [data-testid="stSidebar"] label[data-baseweb="checkbox"] span {
        font-size: 13px !important;
        line-height: 1.3 !important;
    }
    /* 전체선택/해제 버튼 밀착 정렬 */
    [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        gap: 0.4rem !important;
    }
    [data-testid="stSidebar"] button {
        padding: 4px 10px !important;
        font-size: 12.5px !important;
        border-radius: 6px !important;
    }
    /* Expander 아코디언 간격 최적화 */
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        border: 1px solid #E2E8F0 !important;
        border-radius: 6px !important;
        margin-bottom: 4px !important;
        background-color: #F8FAFC !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details summary p {
        font-size: 13px !important;
        font-weight: 700 !important;
        color: #1E293B !important;
    }
    [data-testid="stSidebar"] {
        padding-top: 1rem !important;
    }
    .stButton>button {
        width: 100%;
        background-color: #10B981;
        color: white;
        font-weight: 700;
        border-radius: 6px;
        padding: 0.45rem 0.6rem;
        border: none;
    }
    .stButton>button:hover {
        background-color: #059669;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


# DB 초기화 및 테이블 마이그레이션
init_db()


def main():
    # Header Section
    st.markdown('<div class="main-header">⛳ 네이버 밴드 골프 조인 큐레이터</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">수집 대상 밴드의 비정형 조인글을 Gemini AI가 실시간으로 분석하여 정형 대시보드로 제공합니다.</div>', unsafe_allow_html=True)

    # 1. 세션 만료 상태 사전 검증
    session_valid = SessionManager.is_session_valid()
    if not session_valid:
        st.error(
            "⚠️ **세션 갱신(재로그인) 필요**: 로그인 세션 파일(`band_auth.json`)이 없거나 만료되었습니다.\n\n"
            "• **로컬 PC 환경**: 터미널에서 `python scripts/save_session.py`를 실행해 주세요.\n"
            "• **Streamlit Cloud 웹 배포 환경**: 웹 대시보드의 `Settings` ➔ `Secrets` 탭에 `BAND_AUTH_JSON` 항목으로 `band_auth.json` 파일 내용 전체를 등록하시면 즉시 복원됩니다!"
        )

    # =========================================================================
    # 🔍 SECTION 1: 밴드 수집 및 날짜 타겟 설정 (Scraping & Parsing Input Phase)
    # =========================================================================
    st.sidebar.markdown("### 🔍 1. 밴드 수집 및 날짜 타겟 설정")
    st.sidebar.caption("수집 단계에서 추출할 희망 날짜와 밴드를 먼저 지정합니다.")

    # 📅 희망 티오프 날짜/기간 선택 (수집 파싱 단계 필수 조건)
    today = datetime.now().date()
    date_selection_mode = st.sidebar.radio(
        "📅 수집 희망 날짜 방식",
        ["하루(단일 일자)", "기간(범위 지정)"],
        index=0,
        horizontal=True
    )

    target_start_date_str = None
    target_end_date_str = None

    if date_selection_mode == "하루(단일 일자)":
        single_date = st.sidebar.date_input(
            "📅 수집 희망 날짜 (오늘 이후)",
            value=today,
            min_value=today
        )
        target_start_date_str = single_date.strftime("%Y-%m-%d")
        target_end_date_str = target_start_date_str
    else:
        default_end = today + timedelta(days=21)
        date_range = st.sidebar.date_input(
            "📅 수집 희망 기간 (오늘 이후)",
            value=(today, default_end),
            min_value=today
        )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            target_start_date_str = date_range[0].strftime("%Y-%m-%d")
            target_end_date_str = date_range[1].strftime("%Y-%m-%d")
        elif isinstance(date_range, tuple) and len(date_range) == 1:
            target_start_date_str = date_range[0].strftime("%Y-%m-%d")
            target_end_date_str = target_start_date_str

    # 🔴 선택된 날짜에 대한 대한민국 공휴일 / 대체공휴일 / 주말 빨간색 시각화 안내
    if target_start_date_str:
        try:
            sel_dt = datetime.strptime(target_start_date_str, "%Y-%m-%d").date()
            hol_name = KR_HOLIDAYS.get(sel_dt)
            is_sunday = (sel_dt.weekday() == 6)
            is_saturday = (sel_dt.weekday() == 5)
            
            if hol_name:
                st.sidebar.markdown(f"<div style='color:#DC2626; font-weight:bold; padding:6px 10px; background-color:#FEE2E2; border:1px solid #FCA5A5; border-radius:6px; margin-bottom:12px; font-size:13px;'>🔴 <b>대한민국 공휴일</b>: {hol_name}</div>", unsafe_allow_html=True)
            elif is_sunday:
                st.sidebar.markdown(f"<div style='color:#DC2626; font-weight:bold; padding:6px 10px; background-color:#FEE2E2; border:1px solid #FCA5A5; border-radius:6px; margin-bottom:12px; font-size:13px;'>🔴 <b>일요일 (주말 골프 조인)</b></div>", unsafe_allow_html=True)
            elif is_saturday:
                st.sidebar.markdown(f"<div style='color:#2563EB; font-weight:bold; padding:6px 10px; background-color:#EFF6FF; border:1px solid #BFDBFE; border-radius:6px; margin-bottom:12px; font-size:13px;'>🔵 <b>토요일 (주말 골프 조인)</b></div>", unsafe_allow_html=True)
        except Exception:
            pass

    # 📌 지역 카테고리별 밴드 매핑 정의
    BAND_CATEGORIES = {
        "부산, 경남, 경북": [
            "부산경남경북골프조인",
            "부산경남경북 골프조인",
            "기장동원cc 조인요청방",
            "부산경남골프조인",
            "밀양cc 조인방"
        ],
        "울산근교": [
            "울산 골프 조인동호회",
            "부부커플골프조인",
            "전국 골프조인"
        ],
        "전라, 충청": [
            "전라골프조인",
            "광주전라골프클럽",
            "광주전라골프조인밴드",
            "즐거운 충청/전라골프조인",
            "골프팩토리 대전세종충청골프조인"
        ]
    }

    target_bands = get_target_bands()
    band_options = {b["name"]: b["url"] for b in target_bands}

    # 1. 밴드 개별 토글 세션 키 초기화
    for b in target_bands:
        b_name = b["name"]
        k = f"band_toggle_{b_name}"
        if k not in st.session_state:
            st.session_state[k] = True

    # 2. 카테고리 토글 동기화 콜백 함수
    def update_category_toggle(cat_name):
        cat_key = f"cat_toggle_{cat_name}"
        val = st.session_state[cat_key]
        for b_name in BAND_CATEGORIES[cat_name]:
            st.session_state[f"band_toggle_{b_name}"] = val

    def update_band_toggle(cat_name):
        cat_bands = BAND_CATEGORIES[cat_name]
        all_checked = all(st.session_state.get(f"band_toggle_{bn}", False) for bn in cat_bands)
        st.session_state[f"cat_toggle_{cat_name}"] = all_checked

    # 3. 카테고리 토글 키 초기화
    for cat_name, c_bands in BAND_CATEGORIES.items():
        cat_key = f"cat_toggle_{cat_name}"
        if cat_key not in st.session_state:
            st.session_state[cat_key] = all(st.session_state.get(f"band_toggle_{bn}", True) for bn in c_bands)

    active_count = sum(1 for b in target_bands if st.session_state.get(f"band_toggle_{b['name']}", True))
    st.sidebar.markdown(f"📌 **탐색 밴드 선택 (`{active_count}` / {len(target_bands)}개)**")

    # 전체선택 / 전체해제 버튼 촘촘한 밀착 배치 (3분할 1:1:0.8)
    col_sel1, col_sel2, _ = st.sidebar.columns([1.1, 1.1, 0.8])
    if col_sel1.button("전체 선택"):
        for b in target_bands:
            st.session_state[f"band_toggle_{b['name']}"] = True
        for cat_name in BAND_CATEGORIES:
            st.session_state[f"cat_toggle_{cat_name}"] = True
        st.rerun()

    if col_sel2.button("전체 해제"):
        for b in target_bands:
            st.session_state[f"band_toggle_{b['name']}"] = False
        for cat_name in BAND_CATEGORIES:
            st.session_state[f"cat_toggle_{cat_name}"] = False
        st.rerun()

    selected_band_names = []

    # 4. 카테고리별 아코디언(expander) 컴팩트 렌더링
    for cat_name, c_bands in BAND_CATEGORIES.items():
        cat_key = f"cat_toggle_{cat_name}"
        active_cat_cnt = sum(1 for bn in c_bands if st.session_state.get(f"band_toggle_{bn}", True))
        
        with st.sidebar.expander(f"📂 {cat_name} ({active_cat_cnt}/{len(c_bands)})", expanded=True):
            st.checkbox(
                f"**{cat_name} 전체 선택/해제**",
                key=cat_key,
                on_change=update_category_toggle,
                args=(cat_name,)
            )
            for b_name in c_bands:
                b_key = f"band_toggle_{b_name}"
                is_checked = st.checkbox(
                    f"{b_name}",
                    key=b_key,
                    on_change=update_band_toggle,
                    args=(cat_name,)
                )
                if is_checked:
                    selected_band_names.append(b_name)

    # 🚀 데이터 수집 시작 버튼
    if st.sidebar.button("🚀 선택한 날짜 & 밴드 정보 수집 시작", type="primary"):
        if not selected_band_names:
            st.error("수집할 밴드를 최소 1개 이상 선택해 주세요.")
        elif not session_valid:
            st.error("세션 갱신(재로그인) 필요: 로그인 세션이 유효하지 않습니다.")
        else:
            # 💡 [요구사항 100% 반영]: 새로 수집 시 기존의 과거 수집 DB 결과를 전면 자동 초기화!
            clear_all_joins()

            selected_targets = [{"name": name, "url": band_options[name]} for name in selected_band_names]
            
            date_label = f"'{target_start_date_str}'" if target_start_date_str == target_end_date_str else f"'{target_start_date_str} ~ {target_end_date_str}'"
            
            with st.spinner(f"🕷️ {date_label} 날짜 타겟으로 {len(selected_targets)}개 밴드 크롤링 중... (기존 결과 자동 초기화 완료)"):
                scraper = SelectiveScraper(headless=True)
                raw_posts, is_ok = scraper.scrape_bands(selected_targets)

            if not is_ok:
                st.error("⚠️ 세션 갱신(재로그인) 필요: 세션 만료가 감지되었습니다. 터미널에서 'python scripts/save_session.py'를 실행해 주세요.")
            elif not raw_posts:
                st.info(f"선택하신 {date_label} 날짜 타겟으로 등록된 조인글이 없거나 이미 처리된 게시글입니다.")
            else:
                with st.spinner(f"🤖 AI/하네스 엔진이 {date_label} 지정 날짜의 조인 정보만 선별 정제 중..."):
                    parser = AIParseAgent()
                    all_parsed_details = []
                    for post in raw_posts:
                        details_list = parser.parse_post(
                            raw_text=post["body_text"],
                            band_name=post.get("band_name", "밴드"),
                            author_nickname=post["author_nickname"],
                            post_url=post["post_url"],
                            post_id=post["post_id"],
                            target_start_date=target_start_date_str,
                            target_end_date=target_end_date_str
                        )
                        all_parsed_details.extend(details_list)

                    data_controller = DataControlAgent()
                    saved_cnt = data_controller.process_and_save(all_parsed_details)
                    deleted_cnt = data_controller.run_ttl_cleanup(days_before=3)

                st.success(f"✅ 새로 수집 완료! 기존 결과는 자동 초기화되었으며, {date_label} 신규 조건으로 총 {saved_cnt}건의 정밀 조인 정보가 표출됩니다.")

    # =========================================================================
    # 🎯 SECTION 2: 메인 대시보드 관람 뷰 필터 바 (우측 메인 대시보드 상단 배치)
    # =========================================================================
    st.markdown("### 🎯 대시보드 관람 뷰 필터")
    st.caption("이미 수집된 대시보드 조인 결과를 실시간으로 필터링하고 탐색합니다.")

    # 1줄 필터 컨트롤 바 (지역 / 키워드 / 노캐디 / 부부커플 / DB초기화)
    f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([1.5, 2.0, 1.0, 1.2, 1.0])

    with f_col1:
        region_options = ["전체", "울산,부산", "경남", "대구,경북", "전라", "충청", "서울경기", "강원", "제주"]
        selected_region = st.selectbox("📍 희망 지역 선택", options=region_options, index=0)

    with f_col2:
        keyword_input = st.text_input("🔍 검색 키워드", "", placeholder="구장명/닉네임/밴드명")

    with f_col3:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        only_no_caddie = st.checkbox("🏌️‍♂️ 노캐디만", value=False)

    with f_col4:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        only_couple = st.checkbox("💑 부부/커플만", value=False)

    with f_col5:
        st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
        if st.button("🧹 DB 전체초기화", help="저장된 전체 조인 데이터를 비웁니다."):
            clear_all_joins()
            st.success("DB 데이터가 초기화되었습니다!")
            st.rerun()

    st.markdown("---")

    # =========================================================================
    # 📊 SECTION 3: 메인 대시보드 화면 표출 (수집된 DB 전체 정보 100% 무제한 표출)
    # =========================================================================
    # DB 저장 전체 레코드 (무제한)
    all_unfiltered_records = fetch_golf_joins(ignore_date_filter=True)
    total_db_count = len(all_unfiltered_records)

    # 대시보드 뷰 필터 적용 레코드 (실시간 검색 및 조회)
    records = fetch_golf_joins(
        selected_bands=None,
        keyword=keyword_input,
        region=selected_region,
        only_no_caddie=only_no_caddie,
        only_couple=only_couple,
        ignore_date_filter=True
    )

    filtered_count = len(records)

    # 💡 [필터링 상태 투명 안내 배너]: 2차 뷰 필터(지역/키워드/노캐디 등) 적용 시에만 안내
    if total_db_count > 0 and filtered_count < total_db_count:
        active_filters = []
        if selected_region != "전체":
            active_filters.append(f"희망지역 '{selected_region}'")
        if keyword_input:
            active_filters.append(f"키워드 '{keyword_input}'")
        if only_no_caddie:
            active_filters.append("노캐디")
        if only_couple:
            active_filters.append("부부/커플")

        filter_str = ", ".join(active_filters) if active_filters else "선택한 관람 필터"
        st.info(f"💡 DB에 저장된 **전체 {total_db_count}건** 중 현재 **[{filter_str}]** 관람 조건에 의해 **{filtered_count}건**이 표시 중입니다. (전체 수집건 전량 보기는 '희망지역: 전체' 선택)")

    # 상단 요약 Metric 지표 카드
    col1, col2, col3 = st.columns(3)
    col1.metric("대시보드 조인 검색 건수", f"{filtered_count} 건", delta=f"DB 총 {total_db_count}건 저장됨" if total_db_count != filtered_count else None)
    col2.metric("💑 부부/커플 조인", f"{sum(1 for r in records if r.get('is_couple_possible'))} 건")
    
    avg_fee = int(sum(r['fee'] for r in records)/len(records)) if records else 0
    col3.metric("평균 그린피", f"{avg_fee:,} 원" if avg_fee > 0 else "미상")

    st.markdown("---")

    if not records:
        st.info("💡 저장된 조인 정보가 없습니다. 왼쪽 사이드바에서 희망 날짜와 밴드를 선택한 후 [🚀 선택한 날짜 & 밴드 정보 수집 시작]을 눌러주세요.")
    else:
        df = pd.DataFrame(records)

        df["수집 밴드"] = df["band_name"].apply(lambda x: str(x).strip() if x else "밴드")
        df["그린피(원)"] = df["fee"].apply(lambda x: f"{x:,}원" if x > 0 else "미상/무료")
        df["노캐디"] = df["is_no_caddie"].apply(lambda x: "⭕ 노캐디" if x else "❌")
        df["부부/커플"] = df["is_couple_possible"].apply(lambda x: "⭕ 커플가능" if x else "❌")
        df["지역"] = df["region"].apply(lambda x: x if x else "")

        display_df = df[[
            "수집 밴드", "golf_course", "지역", "date", "time", "그린피(원)", "join_condition",
            "노캐디", "부부/커플"
        ]].copy()

        display_df.columns = [
            "수집 밴드", "골프장", "지역", "날짜", "시간", "그린피", "모집 조건 및 상세",
            "노캐디 여부", "부부/커플"
        ]

        df_event = st.dataframe(
            display_df,
            column_config={
                "수집 밴드": st.column_config.TextColumn("수집 밴드", width="medium"),
                "골프장": st.column_config.TextColumn("골프장", width="medium"),
                "지역": st.column_config.TextColumn("지역", width="small"),
                "날짜": st.column_config.TextColumn("날짜", width="small"),
                "시간": st.column_config.TextColumn("시간", width="small"),
                "그린피": st.column_config.TextColumn("그린피", width="small"),
                "모집 조건 및 상세": st.column_config.TextColumn("모집 조건 및 상세", width="large"),
                "부부/커플": st.column_config.TextColumn("부부/커플", width="small"),
            },
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="dashboard_table_selection"
        )

        # =========================================================================
        # 🔍 원본 텍스트 노랑 하이라이트(Highlight) 열람기 (표 클릭 시 자동 연동)
        # =========================================================================
        st.markdown("---")
        st.markdown("### 🔍 조인글 원본 텍스트 하이라이트(Highlight) 열람기")

        # 대시보드 표에서 클릭한 행 인덱스 자동 감지
        selected_idx = 0
        if df_event and hasattr(df_event, "selection") and df_event.selection:
            selected_rows = df_event.selection.get("rows", [])
            if selected_rows and len(selected_rows) > 0:
                selected_idx = selected_rows[0]

        if selected_idx < len(records):
            sel_r = records[selected_idx]
            st.caption(f"📍 **대시보드 표 선택 감지**: [{sel_r['date']} {sel_r['time']}] {sel_r['golf_course']} ({sel_r['band_name']}) 조인글의 원본 문맥이 노란 형광펜으로 자동 강조 표시됩니다.")
        
        if selected_idx is not None and selected_idx < len(records):
            target_rec = records[selected_idx]
            raw_text = target_rec.get("raw_text") or "원문 텍스트 정보가 없습니다."
            target_time = target_rec.get("time") or ""
            target_course = target_rec.get("golf_course") or ""

            # 원본 텍스트 라인별 노란 형광펜 하이라이트 생성
            raw_lines = raw_text.split("\n")
            highlighted_lines = []
            for line in raw_lines:
                if (target_time and target_time in line) or (target_course and target_course.replace("CC","") in line):
                    highlighted_lines.append(f"<mark style='background-color:#FEF08A; padding:2px 6px; border-radius:4px; font-weight:bold; color:#1E3A8A;'>▶ {line}</mark>")
                else:
                    highlighted_lines.append(line)

            html_rendered = "<br/>".join(highlighted_lines)

            col_view1, col_view2 = st.columns([3, 1])
            with col_view1:
                st.markdown(
                    f"""
                    <div style="background-color:#F8FAFC; border:1px solid #CBD5E1; border-radius:8px; padding:16px; font-family:monospace; line-height:1.7; height:240px; max-height:240px; overflow-y:auto;">
                        {html_rendered}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_view2:
                post_url = target_rec.get("post_url") or ""
                post_link_html = (
                    f'<div style="margin-bottom:12px;"><a href="{post_url}" target="_blank" style="color:#2563EB; font-weight:bold; font-size:14px; text-decoration:none;">🔗 네이버 밴드 원본글 이동</a></div>'
                    if post_url else ''
                )
                fee_val = target_rec.get('fee', 0)
                fee_display = f"{fee_val:,}원" if fee_val > 0 else "미상/무료"
                st.markdown(
                    f"""
                    <div style="background-color:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; padding:16px; height:240px; display:flex; flex-direction:column; justify-content:space-between; box-sizing:border-box;">
                        <div>
                            <div style="font-weight:bold; font-size:16px; color:#1E293B; margin-bottom:8px;">🎯 원본글 빠른 이동</div>
                            {post_link_html}
                        </div>
                        <div style="background-color:#EFF6FF; border:1px solid #BFDBFE; border-radius:6px; padding:12px; font-size:13px; color:#1E40AF; line-height:1.6;">
                            <div>📍 <b>골프장</b>: {target_rec.get('golf_course', '')}</div>
                            <div>📅 <b>날짜</b>: {target_rec.get('date', '')}</div>
                            <div>⏰ <b>시간</b>: {target_rec.get('time', '')}</div>
                            <div>💰 <b>그린피</b>: {fee_display}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )


if __name__ == "__main__":
    main()
