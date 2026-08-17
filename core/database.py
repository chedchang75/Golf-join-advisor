import sqlite3
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from core.schemas import GolfJoinDetail

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "golf_joins.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """데이터베이스 및 테이블 초기화"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS golf_joins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT UNIQUE,
                band_name TEXT DEFAULT '',
                golf_course TEXT NOT NULL,
                region TEXT DEFAULT '',
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                fee INTEGER DEFAULT 0,
                join_condition TEXT,
                is_no_caddie BOOLEAN DEFAULT 0,
                is_couple_possible BOOLEAN DEFAULT 0,
                author_nickname TEXT,
                post_url TEXT,
                raw_text TEXT,
                scraped_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 하위 호환 마이그레이션
        try:
            cursor.execute("ALTER TABLE golf_joins ADD COLUMN region TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE golf_joins ADD COLUMN band_name TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE golf_joins ADD COLUMN is_couple_possible BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("DROP INDEX IF EXISTS idx_golf_schedule")
        except sqlite3.OperationalError:
            pass

        conn.commit()


def check_post_id_exists(post_id: str) -> bool:
    """post_id가 이미 DB에 저장되어 있는지 확인"""
    if not post_id:
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM golf_joins WHERE post_id = ? LIMIT 1", (post_id,))
        return cursor.fetchone() is not None


def save_golf_join(detail: Any) -> bool:
    """정제된 골프 조인 정보를 DB에 적재 (dict 및 GolfJoinDetail 객체 모두 지원)"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # dict / object 속성 추출 헬퍼
    def get_val(obj, key, default=""):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    post_id = get_val(detail, "post_id")
    band_name = get_val(detail, "band_name") or "밴드"
    course_name = get_val(detail, "golf_course")
    region = get_val(detail, "region")
    raw_text = get_val(detail, "raw_text")

    # 🛡️ 라스트 가드: 미상 구장 명칭 소멸 및 강제 구원
    if not course_name or course_name in ["미상 구장", "미상", "알수없음", ""]:
        from core.location_mapper import LocationMapper
        course_name = LocationMapper.infer_course_from_text(raw_text or "", band_name or "")
        if not region:
            region = LocationMapper.get_region(course_name, raw_text or "")

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO golf_joins (
                    post_id, band_name, golf_course, region, date, time, fee, join_condition,
                    is_no_caddie, is_couple_possible, author_nickname, post_url, raw_text, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post_id,
                band_name,
                course_name,
                region or "",
                get_val(detail, "date"),
                get_val(detail, "time"),
                get_val(detail, "fee"),
                get_val(detail, "join_condition"),
                1 if get_val(detail, "is_no_caddie") else 0,
                1 if get_val(detail, "is_couple_possible") else 0,
                get_val(detail, "author_nickname"),
                get_val(detail, "post_url"),
                raw_text,
                get_val(detail, "scraped_at") or now_str
            ))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"DB Error: {e}")
            return False


def clean_duplicate_joins():
    """DB 내 동일한 골프장, 날짜, 시간, 그린피, 밴드를 가진 중복 레코드 정돈 청소"""
    with get_connection() as conn:
        cursor = conn.cursor()
        # 동일 조인건 중복 청소
        cursor.execute("""
            DELETE FROM golf_joins 
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM golf_joins 
                GROUP BY golf_course, date, time, fee, band_name
            )
        """)
        conn.commit()


def fetch_golf_joins(
    selected_bands: Optional[List[str]] = None,
    keyword: Optional[str] = None,
    region: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    only_no_caddie: bool = False,
    only_couple: bool = False,
    ignore_date_filter: bool = True,
    include_unknown_course: bool = True,
    **kwargs
) -> List[Dict[str, Any]]:
    """중복 레코드 0% 정밀 디두플리케이션이 적용된 골프 조인 리스트 반환"""
    clean_duplicate_joins()

    with get_connection() as conn:
        cursor = conn.cursor()
        
        query = """
            SELECT MIN(id) as id, post_id, band_name, golf_course, region, date, time, fee,
                   join_condition, is_no_caddie, is_couple_possible, author_nickname,
                   post_url, raw_text, scraped_at
            FROM golf_joins
            WHERE 1=1
        """
        params: List[Any] = []

        if not include_unknown_course:
            query += " AND golf_course NOT IN ('미상 구장', '미상', '', '알수없음') AND golf_course IS NOT NULL"

        if selected_bands is not None and len(selected_bands) > 0:
            placeholders = ",".join(["?"] * len(selected_bands))
            query += f" AND band_name IN ({placeholders})"
            params.extend(selected_bands)

        if keyword and keyword.strip():
            query += " AND (golf_course LIKE ? OR join_condition LIKE ? OR author_nickname LIKE ? OR region LIKE ? OR band_name LIKE ?)"
            pattern = f"%{keyword.strip()}%"
            params.extend([pattern, pattern, pattern, pattern, pattern])

        if region and region != "전체":
            if region == "울산,부산":
                query += " AND (region LIKE '%부산%' OR region LIKE '%울산%')"
            elif region == "경남":
                query += " AND (region LIKE '%경남%' AND region NOT LIKE '%부산%' AND region NOT LIKE '%울산%')"
            elif region == "대구,경북":
                query += " AND (region LIKE '%경북%' OR region LIKE '%대구%')"
            elif region == "전라":
                query += " AND (region LIKE '%전북%' OR region LIKE '%전남%' OR region LIKE '%광주%')"
            elif region == "충청":
                query += " AND (region LIKE '%충북%' OR region LIKE '%충남%' OR region LIKE '%세종%')"
            elif region == "서울경기":
                query += " AND (region LIKE '%경기%' OR region LIKE '%서울%' OR region LIKE '%인천%')"
            elif region == "강원":
                query += " AND region LIKE '%강원%'"
            elif region == "제주":
                query += " AND region LIKE '%제주%'"
            else:
                query += " AND region LIKE ?"
                params.append(f"%{region}%")

        if start_date and not ignore_date_filter:
            if end_date:
                query += " AND date >= ? AND date <= ?"
                params.extend([start_date, end_date])
            else:
                query += " AND date = ?"
                params.append(start_date)

        if only_no_caddie:
            query += " AND is_no_caddie = 1"

        if only_couple:
            query += " AND is_couple_possible = 1"

        query += " GROUP BY golf_course, date, time, fee ORDER BY date ASC, time ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def delete_expired_joins(days_before: int = 3) -> int:
    """티오프 날짜 기준 N일 지난 구 데이터를 DB에서 자동 삭제 (TTL Janitor)"""
    cutoff_date = (datetime.now() - timedelta(days=days_before)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM golf_joins WHERE date < ?", (cutoff_date,))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


def clear_all_joins():
    """테스트용 과거 적재 데이터 전체 초기화"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM golf_joins")
        conn.commit()
