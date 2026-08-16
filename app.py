import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import importlib

import core.database
import agents.ai_parser
import core.location_mapper
importlib.reload(core.database)
importlib.reload(agents.ai_parser)
importlib.reload(core.location_mapper)

from core.database import init_db, fetch_golf_joins, clear_all_joins
from core.config_loader import get_target_bands
from agents.collector import SessionManager, SelectiveScraper
from agents.ai_parser import AIParseAgent
from agents.data_controller import DataControlAgent

# Streamlit 페이지 기본 설정
st.set_page_config(
    page_title="골프 조인 큐레이터 (Golf Join Curator)",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS 스타일링
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
    [data-testid="stSidebar"] {
        padding-top: 1rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
        gap: 0.4rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stCheckbox"] {
        padding-top: 0px !important;
        padding-bottom: 0px !important;
        margin-bottom: -6px !important;
        font-size: 0.85rem !important;
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
            "👉 터미널에서 `python scripts/save_session.py`를 실행하여 밴드 1회 로그인을 진행해 주세요."
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

    # 🇰🇷 대한민국 주요 공휴일 안내
    st.sidebar.info(
        "🇰🇷 **대한민국 주요 공휴일 참고**\n"
        "• 3/1(삼일절) • 5/5(어린이날) • 5/24(부처님오신날)\n"
        "• 6/6(현충일) • 8/15(광복절) • 9/24~26(추석명절)\n"
        "• 10/3(개천절) • 10/9(한글날) • 12/25(성탄절)"
    )

    # 📌 탐색 밴드 선택 (13개 밴드)
    target_bands = get_target_bands()
    band_options = {b["name"]: b["url"] for b in target_bands}

    col_sel1, col_sel2 = st.sidebar.columns(2)
    select_all = col_sel1.button("전체 선택")
    deselect_all = col_sel2.button("전체 해제")

    for b in target_bands:
        b_name = b["name"]
        key = f"band_toggle_{b_name}"
        if key not in st.session_state:
            st.session_state[key] = True

    if select_all:
        for b in target_bands:
            st.session_state[f"band_toggle_{b['name']}"] = True
    elif deselect_all:
        for b in target_bands:
            st.session_state[f"band_toggle_{b['name']}"] = False

    active_count = sum(1 for b in target_bands if st.session_state.get(f"band_toggle_{b['name']}", True))
    st.sidebar.markdown(f"📌 **탐색 밴드 선택 (`{active_count}` / {len(target_bands)}개)**")

    selected_band_names = []
    col_b1, col_b2 = st.sidebar.columns(2)
    for idx, b in enumerate(target_bands):
        b_name = b["name"]
        key = f"band_toggle_{b_name}"
        target_col = col_b1 if idx % 2 == 0 else col_b2
        
        is_selected = target_col.checkbox(
            f"{b_name}",
            value=st.session_state[key],
            key=key
        )
        if is_selected:
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
                st.error("⚠️ 세션 갱신(재로그인) 필요: 세션 만료가 감지되었습니다.")
            elif not raw_posts:
                st.info("선택한 밴드에 신규 조인글이 없거나 이미 수집된 글입니다.")
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
    # 🎯 SECTION 2: 수집 결과 대시보드 뷰 필터 (Post-Dashboard Filtering Phase)
    # =========================================================================
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 2. 대시보드 관람 뷰 필터")
    st.sidebar.caption("이미 수집된 대시보드 결과물을 다양한 각도로 관람합니다.")

    # 📍 확장된 희망지역 권역 선택 (8개 권역 그룹)
    region_options = ["전체", "울산,부산", "경남", "대구,경북", "전라", "충청", "서울경기", "강원", "제주"]
    selected_region = st.sidebar.selectbox("📍 희망 지역 선택", options=region_options, index=0)

    # 🔍 검색 키워드
    keyword_input = st.sidebar.text_input("🔍 검색 키워드", "", placeholder="구장명/닉네임/밴드명")

    # 🏌️‍♂️ 노캐디만 / 💑 부부커플 조인만
    only_no_caddie = st.sidebar.checkbox("🏌️‍♂️ 노캐디만", value=False)
    only_couple = st.sidebar.checkbox("💑 부부/커플 조인만", value=False)

    st.sidebar.markdown("---")

    # DB 초기화 버튼
    if st.sidebar.button("🧹 DB 데이터 전체 초기화", help="기존 저장 데이터를 비웁니다."):
        clear_all_joins()
        st.sidebar.success("DB가 초기화되었습니다!")
        st.rerun()

    # =========================================================================
    # 📊 SECTION 3: 메인 대시보드 화면 표출 (수집된 DB 전체 정보 100% 무제한 표출)
    # =========================================================================
    # DB 저장 전체 레코드 (무제한)
    all_unfiltered_records = fetch_golf_joins(ignore_date_filter=True)
    total_db_count = len(all_unfiltered_records)

    # 대시보드 뷰 필터 적용 레코드 (1단계 수집 밴드 선택 상태와 관계없이 DB 내 전량 조회)
    records = fetch_golf_joins(
        selected_bands=None,  # 💡 밴드 선택 체크박스로 인해 DB 데이터가 차단되는 현상 완전 해제
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
            "노캐디", "부부/커플", "author_nickname", "post_url"
        ]].copy()

        display_df.columns = [
            "수집 밴드", "골프장", "지역", "날짜", "시간", "그린피", "모집 조건 및 상세",
            "노캐디 여부", "부부/커플", "작성자", "바로가기"
        ]

        # 💡 [바로가기 원본글 빠른 찾기 팁 가이드 배너]
        st.info(
            "💡 **네이버 밴드 원본글 빠른 위치 찾기 팁 (Ctrl + F & 대시보드 표 클릭)**\n"
            "• **대시보드 표에서 원하는 행을 클릭하시면 하단 [🔍 원본 텍스트 하이라이트 열람기]가 드롭다운 클릭 없이 0.1초 만에 자동 활성화됩니다!**\n"
            "• `🔗 바로가기`로 밴드가 열리면 **`Ctrl + F` (페이지 내 찾기)**를 누르고 **`시간(예: 06:30)`**을 검색하시면 1초 만에 해당 줄로 이동합니다!"
        )

        df_event = st.dataframe(
            display_df,
            column_config={
                "수집 밴드": st.column_config.TextColumn("수집 밴드", width="medium"),
                "바로가기": st.column_config.LinkColumn(
                    "바로가기",
                    help="클릭 시 네이버 밴드 원본 게시글 새 창으로 이동",
                    validate="^https://.*",
                    display_text="🔗 글 열기"
                ),
                "골프장": st.column_config.TextColumn("골프장", width="medium"),
                "지역": st.column_config.TextColumn("지역", width="small"),
                "날짜": st.column_config.TextColumn("날짜", width="small"),
                "시간": st.column_config.TextColumn("시간", width="small"),
                "그린피": st.column_config.TextColumn("그린피", width="small"),
                "모집 조건 및 상세": st.column_config.TextColumn("모집 조건 및 상세", width="large"),
                "부부/커플": st.column_config.TextColumn("부부/커플", width="small"),
                "작성자": st.column_config.TextColumn("작성자", width="small"),
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
                    <div style="background-color:#F8FAFC; border:1px solid #CBD5E1; border-radius:8px; padding:16px; font-family:monospace; line-height:1.7; max-height:350px; overflow-y:auto;">
                        {html_rendered}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_view2:
                st.markdown("#### 🎯 원본글 빠른 이동")
                st.code(f"찾기 키워드 (Ctrl+F용):\n{target_time}", language="text")
                if target_rec.get("post_url"):
                    st.markdown(f"[🔗 네이버 밴드 원본글 이동]({target_rec['post_url']})")
                st.info(f"📍 **골프장**: {target_rec['golf_course']}\n📅 **날짜**: {target_rec['date']}\n⏰ **시간**: {target_rec['time']}\n💰 **그린피**: {target_rec['fee']:,}원")


if __name__ == "__main__":
    main()
