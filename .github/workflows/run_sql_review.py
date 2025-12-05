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
# Dify API의 베이스 URL (보통 http://localhost:5001/v1)
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "http://localhost:5001/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
DIFY_WORKFLOW_ID = os.getenv("DIFY_WORKFLOW_ID")


def run(*args) -> str:
    """git 명령 실행 래퍼 함수"""
    return subprocess.check_output(args, text=True)


def get_changed_files() -> List[str]:
    """
    변경된 파일 목록 추출
    - 대상 확장자: .sql, .java, .xml
    - PR: 직전 커밋과 비교
    - fallback: 레포 전체 파일 스캔
    """
    extensions = (".sql", ".java", ".xml")
    
    try:
        # 변경된 파일 목록 가져오기 (HEAD^ vs HEAD)
        out = run("git", "diff", "--name-only", "HEAD^", "HEAD")
        files = [f for f in out.splitlines() if f.endswith(extensions)]
        if files:
            return files
    except subprocess.CalledProcessError:
        pass

    # fallback: 전체 파일 검사
    out = run("git", "ls-files")
    files = [f for f in out.splitlines() if f.endswith(extensions)]
    return files


def extract_sql_from_java(path: str) -> List[str]:
    """
    Java 파일에서 Spring Data JPA @Query("...") 내부의 SQL 추출
    """
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 정규식: @Query 어노테이션 내부의 문자열 추출
    # 예: @Query("SELECT u FROM User u") 또는 @Query(value = "SELECT...", nativeQuery = true)
    # re.DOTALL: 여러 줄에 걸친 쿼리도 매칭
    pattern = r'@Query\s*\(\s*(?:value\s*=\s*)?"([^"]+)"'
    
    matches = re.findall(pattern, content, re.DOTALL)
    
    # 공백 정리 후 반환
    return [m.strip() for m in matches if m.strip()]


def extract_sql_from_xml(path: str) -> List[str]:
    """
    MyBatis Mapper XML 파일에서 SQL 태그(<select>, <insert>, etc) 내용 추출
    """
    if not os.path.exists(path):
        return []

    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        print(f"[WARN] XML 파싱 실패 (유효하지 않은 XML): {path}")
        return []

    sql_list = []
    # MyBatis 주요 태그들
    tags = ['select', 'insert', 'update', 'delete']
    
    # 네임스페이스가 있는 경우를 대비해 iter 사용
    for tag in tags:
        for element in root.iter(tag):
            if element.text:
                # 탭, 엔터 등을 공백 하나로 치환하여 한 줄로 정리
                clean_sql = " ".join(element.text.split())
                if clean_sql:
                    sql_list.append(clean_sql)
    
    return sql_list


def extract_sql_from_file(path: str) -> List[str]:
    """
    파일 확장자에 따라 적절한 추출기(Extractor) 라우팅
    """
    if not os.path.exists(path):
        return []

    _, ext = os.path.splitext(path)
    ext = ext.lower()

    # 1. 순수 SQL 파일
    if ext == '.sql':
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        return [text] if text.strip() else []

    # 2. Java 파일 (JPA @Query)
    elif ext == '.java':
        return extract_sql_from_java(path)

    # 3. MyBatis XML 파일
    elif ext == '.xml':
        return extract_sql_from_xml(path)

    return []


def call_dify_workflow(sql: str) -> str:
    """
    Dify Workflow 실행 API 호출.
    - /workflows/run 엔드포인트 사용 (API Key로 워크플로우 식별)
    """
    if not DIFY_API_KEY:
        raise RuntimeError("DIFY_API_KEY 환경 변수가 설정되어 있지 않습니다.")

    # ✅ URL 수정 완료: Workflow ID 제거
    url = f"{DIFY_API_BASE.rstrip('/')}/workflows/run"

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {
            "sql_code": sql,
        },
        "response_mode": "blocking",
        "user": os.getenv("GITHUB_ACTOR", "github-sql-review"),
    }

    print(f"[sql-review] call Dify workflow: {url}")
    
    # Timeout 90초 설정
    resp = requests.post(url, headers=headers, json=payload, timeout=90)

    print(f"[sql-review] Dify status: {resp.status_code}")
    
    try:
        data = resp.json()
    except Exception:
        print("[sql-review] ❌ Dify 응답 JSON 파싱 실패, raw text:")
        print(resp.text)
        resp.raise_for_status()
        return ""

    if not resp.ok:
        raise RuntimeError(f"Dify error: HTTP {resp.status_code}, body={data}")

    # Dify 응답 구조 파싱 (markdown_report 우선)
    outputs = data.get("data", {}).get("outputs", {})
    report_obj = (
        outputs.get("markdown_report")
        or outputs.get("report")
        or outputs.get("text")
    )

    if isinstance(report_obj, dict):
        return str(report_obj.get("value", ""))
    if report_obj is None:
        return ""
    return str(report_obj)


def is_rejected(report_markdown: str) -> bool:
    """
    리포트 텍스트 안에서 '반려' 키워드 감지
    """
    return "상태" in report_markdown and "**반려**" in report_markdown


def main() -> None:
    # 1. 변경된 파일 중 SQL, Java, XML 추출
    changed_files = get_changed_files()
    extensions = (".sql", ".java", ".xml")
    target_files = [f for f in changed_files if f.endswith(extensions)]

    if not target_files:
        print("[sql-review] 검사 대상 파일(SQL/Java/XML)이 없습니다. 통과.")
        with open("sql_review_report.md", "w", encoding="utf-8") as f:
            f.write("# SQL Review Report\n\n변경된 검사 대상 파일이 없습니다.\n")
        return

    print(f"[sql-review] 검사 대상 파일: {target_files}")

    any_rejected = False
    report_sections: List[str] = []

    # 2. 각 파일에서 SQL 추출 후 Dify 점검
    for path in target_files:
        sql_snippets = extract_sql_from_file(path)
        
        if not sql_snippets:
            print(f"[sql-review] {path}: 추출된 SQL 없음. 건너뜀.")
            continue

        for idx, sql in enumerate(sql_snippets, start=1):
            # 너무 긴 SQL은 로그에서 잘라서 보여줌
            preview = sql[:100].replace('\n', ' ')
            print(f"[sql-review] ---- {path} (snippet #{idx}): {preview} ... ----")

            try:
                report_md = call_dify_workflow(sql)
            except Exception as e:
                msg = f"❌ Dify workflow 호출 실패: {e}"
                print(msg)
                report_sections.append(
                    f"## 📄 파일: `{path}` (snippet #{idx})\n\n{msg}\n"
                )
                any_rejected = True
                continue

            if not report_md.strip():
                report_md = "_(Dify 리포트 내용 없음)_"

            # 리포트 섹션 생성
            section = (
                f"---\n\n"
                f"## 📄 파일: `{path}` (snippet #{idx})\n\n"
                f"```sql\n{sql}\n```\n\n"
                f"{report_md}\n"
            )
            report_sections.append(section)

            if is_rejected(report_md):
                any_rejected = True

    # 3. 최종 리포트 파일 생성
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

    # 4. 실패 시 Exit Code 1 반환 (GitHub Actions 실패 처리)
    if any_rejected:
        sys.exit(1)


if __name__ == "__main__":
    main()
