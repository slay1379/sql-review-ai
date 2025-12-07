import os
import re
import subprocess
import sys
import glob
import requests
import xml.etree.ElementTree as ET
from typing import List

# --- 설정 ---
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "http://localhost:5001/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")

# 검사할 확장자
TARGET_EXTENSIONS = ('.sql', '.java', '.xml', '.py')

def run_command(*args) -> str:
    try:
        return subprocess.check_output(args, text=True).strip()
    except subprocess.CalledProcessError:
        return ""

def get_changed_files() -> List[str]:
    files = set()
    # 1. Diff 확인
    try:
        diff_out = run_command("git", "diff", "--name-only", "HEAD^", "HEAD")
        files.update(diff_out.splitlines())
    except: pass
    
    # 2. 로컬/Fallback 확인
    if not files:
        for ext in TARGET_EXTENSIONS:
            files.update(glob.glob(f"**/*{ext}", recursive=True))

    return [f for f in files if f.endswith(TARGET_EXTENSIONS) and os.path.exists(f)]

def get_file_contents(path: str) -> List[str]:
    # 1. XML 처리
    if path.endswith('.xml'):
        try:
            tree = ET.parse(path)
            sql_list = []
            for tag in ['select', 'insert', 'update', 'delete']:
                for el in tree.getroot().iter(tag):
                    if el.text:
                        # ✨ 수정됨: XML 내용도 마스킹 처리
                        clean_sql = mask_pii(el.text.strip())
                        sql_list.append(f"\n{clean_sql}")
            return sql_list
        except: return []
    
    # 2. Java, Python, SQL 등 일반 파일 처리
    try:
        # 대용량 파일 처리 로직이 있다면 거기에도 적용해야 합니다.
        # 여기서는 기본 로직 기준으로 설명합니다.
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # ✨ 핵심 수정 포인트! ✨
            # AI에게 보내기 전에 마스킹 함수를 먼저 통과시킵니다.
            masked_content = mask_pii(content)
            
            # (대용량 파일 처리 로직이 있다면 masked_content를 넘기세요)
            return [masked_content] if masked_content.strip() else []
            
    except Exception as e:
        print(f"[Error] Reading {path}: {e}")
        return []

def call_dify_workflow(content: str, file_name: str) -> str:
    url = f"{DIFY_API_BASE.rstrip('/')}/workflows/run" # 또는 /chat-messages (앱 유형에 따라 다름)
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}
    
    # 입력 변수 'sql_code'로 통일
    payload = {
        "inputs": {"sql_code": content, "file_name": file_name},
        "response_mode": "blocking",
        "user": "github-bot"
    }
    
    try:
        print(f"[sql-review] Sending {file_name} to Dify...")
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if not resp.ok:
            print(f"[Error] API Status: {resp.status_code}")
            return f"❌ API 오류: {resp.status_code}"

        data = resp.json()
        
        # ✨ [디버깅용 로그 추가] ✨ 
        # 이 로그가 깃허브 액션에 찍히면 원인을 바로 알 수 있습니다.
        print(f"🔥 [DEBUG] Dify Raw Response: {data}") 

        outputs = data.get("data", {}).get("outputs", {})
        data = resp.json()

        # 응답 파싱 (Workflow vs ChatApp 호환성 확보)
        outputs = data.get("data", {}).get("outputs", {})
        result = (
            outputs.get("text") or 
            outputs.get("markdown_report") or 
            outputs.get("result") or
            data.get("answer") or # Chat App일 경우
            ""
        )
        
        if not result:
            print(f"[WARN] Empty response from Dify. Raw: {data}")
            return "❌ AI 응답이 비어있습니다. (설정 확인 필요)"
            
        return str(result)
        
    except Exception as e:
        return f"❌ 연결 오류: {str(e)}"

def is_rejected(report_markdown: str) -> bool:
    """
    리포트 텍스트에서 '반려' 또는 '실패'를 의미하는 키워드를 강력하게 검색합니다.
    """
    if not report_markdown:
        return False

    # 검출할 키워드 목록 (하나라도 있으면 Fail 처리)
    # AI가 테이블 포맷, 리스트 포맷 등 다양하게 줄 수 있으므로 핵심 단어 위주로 등록
    failure_keywords = [
        "반려",              # 가장 확실한 키워드
        "상태: 반려",
        "상태: Fail",
        "Status: Reject",
        "Status: Fail",
        "치명적인",           # "치명적인 스키마 오류" 등
        "Critical",          # 영어권 응답 대비
        "보안 위험",          # "보안 위험 (High/Medium)"
        "Security Risk",
        "스키마 불일치",       # "치명적인 스키마 불일치"
        "Schema Mismatch"
    ]
    
    # 텍스트 내에 키워드가 하나라도 포함되어 있는지 확인
    for keyword in failure_keywords:
        if keyword in report_markdown:
            print(f"[sql-review] 반려 키워드 감지됨: '{keyword}'")
            return True

    return False

def mask_pii(text: str) -> str:
    """
    소스코드 내의 민감정보(PII)를 찾아 마스킹 처리합니다.
    """
    if not text:
        return text

    # 1. 주민등록번호 (외국인등록번호 포함) 패턴
    # 예: 900101-1234567 또는 9001011234567 -> 900101-*******
    # 설명: 앞6자리 + 구분자(-, 공백, 없음) + 뒤7자리 (1~4로 시작)
    rrn_pattern = r'(?<!\d)(\d{6})[-\s]*([1-4]\d{6})(?!\d)'
    text = re.sub(rrn_pattern, r'\1-*******', text)

    # 2. 휴대전화번호 패턴
    # 예: 010-1234-5678 또는 01012345678 -> 010-****-5678
    phone_pattern = r'(01[016789])[-.\s]?(\d{3,4})[-.\s]?(\d{4})'
    text = re.sub(phone_pattern, r'\1-****-\3', text)

    # 3. 이메일 주소 패턴
    # 예: user@example.com -> ***@example.com
    # 설명: @ 앞부분을 무조건 ***로 치환
    email_pattern = r'([a-zA-Z0-9._%+-]+)(@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    text = re.sub(email_pattern, r'***\2', text)

    return text

def main():
    target_files = get_changed_files()
    # 불필요한 파일 제외
    target_files = [f for f in target_files if "node_modules" not in f and ".github" not in f]
    
    print(f"[sql-review] Files to check: {target_files}")

    if not target_files:
        with open("sql_review_report.md", "w") as f: f.write("변경 파일 없음")
        return

    report_content = []
    has_failure = False

    for fpath in target_files:
        contents = get_file_contents(fpath)
        for content in contents:
            res = call_dify_workflow(content, fpath)
            # 결과가 있든 없든 헤더와 함께 기록 (그래야 빈 리포트 방지)
            report_content.append(f"## 📄 `{fpath}`\n\n{res}\n\n---")
            if is_rejected(res): has_failure = True

    with open("sql_review_report.md", "w", encoding="utf-8") as f:
        status = "🚫 **반려된 코드가 있습니다.**" if has_failure else "✅ **모든 코드 통과**"
        f.write(f"# SQL Review Report\n\n### 전체 상태: {status}\n\n")
        if not report_content:
            f.write("검출된 코드가 없어 리포트가 비어있습니다.")
        else:
            f.write("\n".join(report_content))

    if has_failure: sys.exit(1)

if __name__ == "__main__":
    main()
