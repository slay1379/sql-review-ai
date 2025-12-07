import os
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
    # XML만 태그 추출, 나머지는 통째로 읽기
    if path.endswith('.xml'):
        try:
            tree = ET.parse(path)
            sql_list = []
            for tag in ['select', 'insert', 'update', 'delete']:
                for el in tree.getroot().iter(tag):
                    if el.text: sql_list.append(f"\n{el.text.strip()}")
            return sql_list
        except: return []
    
    # Java, Python, SQL 등
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            return [content] if content else []
    except: return []

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

def is_rejected(text: str) -> bool:
    # 반려 키워드 체크
    return any(k in text for k in ["상태: 반려", "상태: Fail", "Status: Fail", "심각한", "취약점"])

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
