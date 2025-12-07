import os
import subprocess
import sys
import glob
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict

# --- 설정 ---
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "http://localhost:5001/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
DIFY_WORKFLOW_ID = os.getenv("DIFY_WORKFLOW_ID")

# 검사할 파일 확장자 목록
TARGET_EXTENSIONS = ('.sql', '.java', '.xml', '.py')

def run_command(*args) -> str:
    try:
        return subprocess.check_output(args, text=True).strip()
    except subprocess.CalledProcessError:
        return ""

def get_changed_files() -> List[str]:
    """
    Git에서 변경된 파일 목록을 가져옵니다. (Push 및 PR 상황 모두 대응)
    """
    files = set()
    
    # 1. PR 또는 커밋 간 변경사항 확인 (HEAD^ vs HEAD)
    # 첫 커밋이거나 오류 발생 시 무시
    try:
        diff_out = run_command("git", "diff", "--name-only", "HEAD^", "HEAD")
        files.update(diff_out.splitlines())
    except Exception:
        pass

    # 2. Staged 상태인 파일 확인 (로컬 테스트용)
    try:
        diff_cached = run_command("git", "diff", "--name-only", "--cached")
        files.update(diff_cached.splitlines())
    except Exception:
        pass

    # 3. 만약 Git 명령어가 안 먹히거나 파일이 없으면, 현재 폴더의 모든 대상 파일 스캔 (Fallback)
    if not files:
        for ext in TARGET_EXTENSIONS:
            files.update(glob.glob(f"**/*{ext}", recursive=True))

    # 확장자 필터링 및 존재 여부 확인
    valid_files = [
        f for f in files 
        if f.endswith(TARGET_EXTENSIONS) and os.path.exists(f)
    ]
    return sorted(list(set(valid_files)))

def extract_content_from_xml(path: str) -> List[str]:
    """
    MyBatis XML 파일에서 SQL 태그 내용만 추출
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        print(f"[WARN] XML 파싱 실패: {path}")
        return []

    sql_list = []
    # MyBatis 주요 태그
    tags = ['select', 'insert', 'update', 'delete']
    
    for tag in tags:
        for element in root.iter(tag):
            # 텍스트가 있는 경우 공백 정리 후 추가
            if element.text:
                clean_sql = " ".join(element.text.split())
                if clean_sql:
                    sql_list.append(f"\n{clean_sql}")
    
    return sql_list

def get_file_contents(path: str) -> List[str]:
    """
    파일 확장자에 따라 내용을 적절히 가공하여 반환
    """
    if not os.path.exists(path):
        return []

    _, ext = os.path.splitext(path)
    ext = ext.lower()

    # 1. XML (MyBatis): 태그만 추출 (토큰 절약)
    if ext == '.xml':
        return extract_content_from_xml(path)

    # 2. Java, Python, SQL: 파일 전체 읽기
    # 이유: Java/Python은 정규식으로 SQL을 완벽히 추출하기 어렵습니다.
    # LLM에게 전체 코드를 주면 변수 맥락까지 파악하여 더 정확히 리뷰합니다.
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip():
                return []
            return [content]
    except Exception as e:
        print(f"[Error] 파일 읽기 실패 {path}: {e}")
        return []

def call_dify_workflow(content: str, file_name: str) -> str:
    if not DIFY_API_KEY:
        raise RuntimeError("DIFY_API_KEY 환경 변수가 없습니다.")

    url = f"{DIFY_API_BASE.rstrip('/')}/workflows/run"
    
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Dify Workflow 입력 변수 설정
    # 주의: Dify 워크플로우의 '시작' 블록에 설정된 변수명과 일치해야 합니다.
    # 여기서는 범용성을 위해 'sql_code'로 통일해서 보냅니다.
    payload = {
        "inputs": {
            "sql_code": content,      # 코드 내용
            "file_name": file_name    # 파일명 (참고용)
        },
        "response_mode": "blocking",
        "user": os.getenv("GITHUB_ACTOR", "github-action-bot"),
    }

    print(f"[sql-review] Sending to Dify... ({file_name})")
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        
        if not resp.ok:
            print(f"[Error] Dify API Fail: {resp.status_code} - {resp.text}")
            return f"❌ Dify API 오류: {resp.status_code}"

        data = resp.json()
        
        # Dify 응답 파싱 (워크플로우 출력 변수명에 따라 다를 수 있음)
        # 우선순위: data > outputs > text / markdown_report / answer
        outputs = data.get("data", {}).get("outputs", {})
        result = (
            outputs.get("text") or 
            outputs.get("markdown_report") or 
            outputs.get("report") or 
            outputs.get("result") or
            ""
        )
        
        return str(result)

    except Exception as e:
        print(f"[Error] Connection Fail: {e}")
        return f"❌ 연결 오류: {str(e)}"

def is_rejected(report_markdown: str) -> bool:
    """
    리포트 내용을 분석하여 반려 여부를 결정합니다.
    단순 키워드 매칭이 아니라, 문맥이나 명확한 상태 표시를 찾도록 개선했습니다.
    """
    # 1. 확실한 반려 멘트가 있는지 확인
    failure_indicators = [
        "상태: 반려",
        "상태: Fail",
        "Status: Reject",
        "Status: Fail",
        "심각한 보안 위협", # 단순 '위험' 단어 제외
        "SQL Injection 취약점이 발견",
        "권한 우회 가능성",
        "스키마 불일치 (치명적)"
    ]
    
    for indicator in failure_indicators:
        if indicator in report_markdown:
            return True
            
    # 2. '승인'이라는 단어가 있지만 '조건부'인 경우는 통과로 처리 (사용자 정책에 따라 변경 가능)
    # 만약 '조건부 승인'도 반려하고 싶다면 아래 주석을 해제하세요.
    # if "승인(조건부)" in report_markdown:
    #     return True

    return False

def main():
    target_files = get_changed_files()
    
    # 노드 모듈, 깃 설정 등 불필요한 파일 제외
    target_files = [f for f in target_files if "node_modules" not in f and ".github" not in f]

    if not target_files:
        print("[sql-review] 검사 대상 파일이 없습니다.")
        with open("sql_review_report.md", "w", encoding="utf-8") as f:
            f.write("# SQL Review Report\n\n변경된 검사 대상 파일이 없습니다.\n")
        return

    print(f"[sql-review] 검사 대상 파일 목록: {target_files}")

    report_content = []
    has_failure = False

    for file_path in target_files:
        # 파일 내용 가져오기 (List 형태 반환)
        contents = get_file_contents(file_path)

        for idx, content in enumerate(contents):
            # Dify 호출
            review_result = call_dify_workflow(content, file_path)
            
            # 리포트 섹션 작성
            snippet_info = f"(Snippet #{idx+1})" if len(contents) > 1 else ""
            section = (
                f"---\n"
                f"## 📄 `{file_path}` {snippet_info}\n\n"
                f"{review_result}\n\n"
            )
            report_content.append(section)

            # 반려 여부 체크
            if is_rejected(review_result):
                has_failure = True

    # 최종 리포트 파일 생성
    with open("sql_review_report.md", "w", encoding="utf-8") as f:
        status_icon = "🚫" if has_failure else "✅"
        status_text = "반려된 코드가 있습니다." if has_failure else "모든 코드 통과"
        
        f.write("# SQL Review Report\n\n")
        f.write(f"### 전체 상태: {status_icon} **{status_text}**\n\n")
        
        if not report_content:
            f.write("검출된 코드가 없어 리포트가 비어있습니다.\n")
        else:
            f.write("\n".join(report_content))

    # 실패 시 Exit Code 1 반환 -> GitHub Action 실패 처리
    if has_failure:
        print("[sql-review] 🚫 Critical issues found. Failing the job.")
        sys.exit(1)
    else:
        print("[sql-review] ✅ All checks passed.")

if __name__ == "__main__":
    main()
