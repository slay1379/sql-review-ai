import os
import subprocess
import textwrap
import json
import sys
import re
import xml.etree.ElementTree as ET
from typing import List

import requests

# --- Dify API 설정 ---
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "http://localhost:5001/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
DIFY_WORKFLOW_ID = os.getenv("DIFY_WORKFLOW_ID")


def run(*args) -> str:
    return subprocess.check_output(args, text=True)


def get_changed_files() -> List[str]:
    extensions = (".sql", ".java", ".xml")
    try:
        out = run("git", "diff", "--name-only", "HEAD^", "HEAD")
        files = [f for f in out.splitlines() if f.endswith(extensions)]
        if files:
            return files
    except subprocess.CalledProcessError:
        pass

    out = run("git", "ls-files")
    files = [f for f in out.splitlines() if f.endswith(extensions)]
    return files


def extract_sql_from_java(path: str) -> List[str]:
    """
    Java 파일에서 @Query 내부의 SQL 추출 (Text Block 지원 추가)
    """
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 정규식 수정: """ (Text Block) 또는 " (String) 모두 매칭
    # Group 1: """ ... """ 내용
    # Group 2: " ... " 내용
    pattern = r'@Query\s*\(\s*(?:value\s*=\s*)?(?:"""(.*?)"""|"([^"]+)")'
    
    matches = re.findall(pattern, content, re.DOTALL)
    
    results = []
    for m in matches:
        # m은 ('SQL내용', '') 또는 ('', 'SQL내용') 형태임
        sql = m[0] if m[0] else m[1]
        if sql.strip():
            results.append(sql.strip())
            
    return results


def extract_sql_from_xml(path: str) -> List[str]:
    if not os.path.exists(path):
        return []

    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        print(f"[WARN] XML 파싱 실패: {path}")
        return []

    sql_list = []
    tags = ['select', 'insert', 'update', 'delete']
    
    for tag in tags:
        for element in root.iter(tag):
            if element.text:
                clean_sql = " ".join(element.text.split())
                if clean_sql:
                    sql_list.append(clean_sql)
    
    return sql_list


def extract_sql_from_file(path: str) -> List[str]:
    if not os.path.exists(path):
        return []

    _, ext = os.path.splitext(path)
    ext = ext.lower()

    if ext == '.sql':
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        return [text] if text.strip() else []

    elif ext == '.java':
        return extract_sql_from_java(path)

    elif ext == '.xml':
        return extract_sql_from_xml(path)

    return []


def call_dify_workflow(sql: str) -> str:
    if not DIFY_API_KEY:
        raise RuntimeError("DIFY_API_KEY 환경 변수가 설정되어 있지 않습니다.")

    url = f"{DIFY_API_BASE.rstrip('/')}/workflows/run"

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {"sql_code": sql},
        "response_mode": "blocking",
        "user": os.getenv("GITHUB_ACTOR", "github-sql-review"),
    }

    print(f"[sql-review] call Dify workflow: {url}")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        print(f"[sql-review] Dify status: {resp.status_code}")
        
        if not resp.ok:
            print(f"Error body: {resp.text}")
            resp.raise_for_status()
            
        data = resp.json()
        outputs = data.get("data", {}).get("outputs", {})
        report_obj = outputs.get("markdown_report") or outputs.get("report") or outputs.get("text")

        if isinstance(report_obj, dict):
            return str(report_obj.get("value", ""))
        return str(report_obj) if report_obj else ""
        
    except Exception as e:
        print(f"[sql-review] ❌ Error: {e}")
        raise


def is_rejected(report_markdown: str) -> bool:
    return "상태" in report_markdown and "**반려**" in report_markdown


def main() -> None:
    changed_files = get_changed_files()
    target_files = [f for f in changed_files if f.endswith((".sql", ".java", ".xml"))]

    if not target_files:
        print("[sql-review] 검사 대상 파일 없음.")
        with open("sql_review_report.md", "w", encoding="utf-8") as f:
            f.write("# SQL Review Report\n\n변경된 검사 대상 파일이 없습니다.\n")
        return

    print(f"[sql-review] 검사 대상: {target_files}")

    any_rejected = False
    report_sections: List[str] = []

    for path in target_files:
        sql_snippets = extract_sql_from_file(path)
        
        if not sql_snippets:
            print(f"[sql-review] {path}: 추출된 SQL 없음 (Skipping)")
            continue

        for idx, sql in enumerate(sql_snippets, start=1):
            print(f"[sql-review] Detecting SQL in {path}...")
            try:
                report_md = call_dify_workflow(sql)
            except Exception:
                report_md = "❌ Dify 분석 중 오류 발생"
                any_rejected = True

            section = (
                f"---\n\n"
                f"## 📄 파일: `{path}` (snippet #{idx})\n\n"
                f"```sql\n{sql}\n```\n\n"
                f"{report_md}\n"
            )
            report_sections.append(section)

            if is_rejected(report_md):
                any_rejected = True

    with open("sql_review_report.md", "w", encoding="utf-8") as f:
        if any_rejected:
            summary = "전체 상태: 🚫 **반려된 SQL이 있습니다.**\n"
        else:
            summary = "전체 상태: ✅ **모든 SQL 통과**\n"

        f.write("# SQL Review Report\n\n")
        f.write(f"- {summary}\n\n")
        
        if not report_sections:
             f.write("검출된 SQL 구문이 없어 리포트가 비어있습니다.\n")
        else:
            f.write("\n".join(report_sections))

    if any_rejected:
        sys.exit(1)


if __name__ == "__main__":
    main()
