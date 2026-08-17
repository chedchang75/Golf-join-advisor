import json
import os
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SELECTORS_PATH = os.path.join(BASE_DIR, "selectors.json")


def load_config() -> Dict[str, Any]:
    """config.json 파일 로드"""
    if not os.path.exists(CONFIG_PATH):
        return {"target_bands": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_selectors() -> Dict[str, str]:
    """selectors.json 파일 로드"""
    default_selectors = {
        "post_card": "div[data-viewname='DPostItemView']",
        "body_text": ".bodyText",
        "author_name": ".name",
        "post_time_link": "a.time"
    }
    if not os.path.exists(SELECTORS_PATH):
        return default_selectors
    with open(SELECTORS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        if "selectors" in data and isinstance(data["selectors"], dict):
            return data["selectors"]
        return data if isinstance(data, dict) else default_selectors


def get_target_bands() -> List[Dict[str, str]]:
    """수집 대상 밴드 목록 반환"""
    cfg = load_config()
    return cfg.get("target_bands", [])
