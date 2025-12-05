# .github/workflows/run_sql_review.py
import os
import subprocess
import textwrap
import json
import sys
from typing import List

import requests

# --- Dify API 설정 ---
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "http://localhost:5001")
DIFY_API_KEY = os.environ["DIFY_API_KEY"]  # 없으면 바로 에러 나도록


def run(*args) -> str:
    """git 명령 래퍼"""
    return subprocess.check_output(args, text=True)


def get_changed_files() -> List[str]:
    """
    변경된 파일 목록에서 SQL 관련 파일만 추출
    - PR: 직전 커밋과 비교
    - fallback: 레포 전체에서 *.sql
    """
    try:
        out = run("git", "diff", "--name-only", "HEAD^", "HEAD")
        files = [f for f in out.splitlines() if f.endswith(".sql")]
        if files:
            return files
    except subprocess.CalledProcessError:
        pass

    out = run("git", "ls-files")
    files = [f for f in out.splitlines() if f.endswith(".sql")]
    return files


def extract_sql_from_file(path: str) -> List[str]:
    """
    지금은 .sql 파일만 대상:
      - 파일 전체를 하나의 SQL snippet으로 본다
    나중에 필요하면 여러 쿼리 분리 로직 추가 가능
    """
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if not text.strip():
        return []

    return [text]


def call_dify_workflow(sql: str) -> str:
    """
    Dify Workflow 실행 API 호출.
    - inputs.sql_code 에 SQL 전달
    - blocking 모드로 리포트 마크다운을 받아온다.
    """
    url = f"{DIFY_API_BASE.rstrip('/')}/workflows/run"
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {
            "sql_code": sql,
            # 필요하면 여기서 schema_context 등 다른 변수도 함께 보냄
        },
        "response_mode": "blocking",
        "user": os.getenv("GITHUB_ACTOR", "github-sql-review"),
    }

    print(f"[sql-review] call Dify workflow: {url}")
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    outputs = data.get("data", {}).get("outputs", {})
    report_obj = outputs.get("markdown_report") or outputs.get("report") or outputs.get("text")

    if isinstance(report_obj, dict):
        return str(report_obj.get("value", ""))
    if report_obj is None:
        return ""
    return str(report_obj)


def is_rejected(report_markdown: str) -> bool:
    """
    리포트 텍스트 안에서 '반려' 여부를 간단히 판별.
    - Dify 리포트 템플릿이 바뀌면 여기만 조정하면 됨.
    """
    return "상태" in report_markdown and "**반려**" in report_markdown


def main() -> None:
    changed_files = get_changed_files()
    target_files = [f for f in changed_files if f.endswith(".sql")]

    if not target_files:
        print("[sql-review] SQL 관련 변경 파일 없음. 통과.")
        # 그래도 빈 리포트 파일 하나 만들어 둔다
        with open("sql_review_report.md", "w", encoding="utf-8") as f:
            f.write("# SQL Review Report\n\n변경된 SQL 파일이 없습니다.\n")
        return

    print(f"[sql-review] SQL 후보 파일: {target_files}")

    any_rejected = False
    report_sections: List[str] = []

    for path in target_files:
        sql_snippets = extract_sql_from_file(path)
        if not sql_snippets:
            continue

        for idx, sql in enumerate(sql_snippets, start=1):
            print(f"[sql-review] ---- {path} (snippet #{idx}) ----")
            print(textwrap.indent(sql[:400], prefix="    "))

            try:
                report_md = call_dify_workflow(sql)
            except Exception as e:
                # Dify 호출 자체가 실패하면 이 PR은 막는게 안전
                msg = f"❌ Dify workflow 호출 실패: {e}"
                print(msg)
                report_sections.append(
                    f"## 파일: `{path}` (snippet #{idx})\n\n"
                    f"{msg}\n"
                )
                any_rejected = True
                continue

            if not report_md.strip():
                report_md = "_(Dify 쪽에서 리포트를 반환하지 않았습니다)_"

            # PR 코멘트에서 파일/스니펫 구분용 래핑만 하고,
            # 본문 내용은 Dify 리포트를 그대로 사용
            section = (
                f"---\n\n"
                f"## 📄 파일: `{path}` (snippet #{idx})\n\n"
                f"{report_md}\n"
            )
            report_sections.append(section)

            if is_rejected(report_md):
                any_rejected = True

    # 최종 마크다운 리포트 파일 생성
    with open("sql_review_report.md", "w", encoding="utf-8") as f:
        if any_rejected:
            summary = "전체 상태: 🚫 **반려된 SQL이 있습니다.**\n"
        else:
            summary = "전체 상태: ✅ **모든 SQL 통과**\n"

        f.write("# SQL Review Report\n\n")
        f.write(f"- {summary}\n\n")
        f.write("\n".join(report_sections))

    if any_rejected:
        # 실패로 처리 (하지만 GitHub Actions에서 continue-on-error로
        # 코멘트는 남기고, 마지막에 이 코드로 fail 시킬거야)
        sys.exit(1)


if __name__ == "__main__":
    main()
