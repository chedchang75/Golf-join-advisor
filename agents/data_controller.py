from typing import List, Set, Tuple
from core.schemas import GolfJoinDetail
from core.database import save_golf_join, delete_expired_joins, check_post_id_exists


class PostDeduplicator:
    """[Agent 3 - Post_Deduplicator] 수집 중 중복 데이터 제어 스킬"""

    def __init__(self):
        # 메모리 상에서 이번 수집 주기 내 중복 방지용 Key Set
        self.seen_schedules: Set[Tuple[str, str, str]] = set()

    def is_duplicate_in_session(self, detail: GolfJoinDetail) -> bool:
        """동일 수집 주기 내 (golf_course, date, time) 중복 검사"""
        key = (detail.golf_course.strip().lower(), detail.date, detail.time)
        if key in self.seen_schedules:
            return True
        self.seen_schedules.add(key)
        return False

    @staticmethod
    def is_already_in_db(post_id: str) -> bool:
        """DB 영구 적재 여부 체크 (조기 종료용)"""
        return check_post_id_exists(post_id)


class DataControlAgent:
    """[Agent 3 - Data Control Agent] 데이터 입출력 정밀도 유지 및 수명 관리 에이전트"""

    def __init__(self):
        self.deduplicator = PostDeduplicator()

    def process_and_save(self, details: List[GolfJoinDetail]) -> int:
        """
        정제된 조인 정보 리스트를 받아서 중복 제거 후 DB 적재.
        저장된 개수 반환.
        """
        saved_count = 0
        for item in details:
            # 메모리 내 중복 검사
            if self.deduplicator.is_duplicate_in_session(item):
                print(f"Skip Session Duplicate Schedule: {item.golf_course} {item.date} {item.time}")
                continue

            # DB 적재
            if save_golf_join(item):
                saved_count += 1

        return saved_count

    def run_ttl_cleanup(self, days_before: int = 3) -> int:
        """[TTL_Janitor] 티오프 날짜 기준 N일 이상 경과된 데이터 자동 삭제"""
        deleted_count = delete_expired_joins(days_before=days_before)
        print(f"TTL Janitor Cleared {deleted_count} expired golf join records (older than {days_before} days).")
        return deleted_count
