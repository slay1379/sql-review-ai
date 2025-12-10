import os
import re
import subprocess
import sys
import glob
import requests
import xml.etree.ElementTree as ET
from typing import List, Tuple

# --- 설정 ---
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "http://localhost:5001/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
MAX_FULL_SCAN_LINES = 300  # 이 줄 수보다 적으면 전체 스캔, 많으면 부분 스캔
CONTEXT_PADDING = 20       # 변경된 라인 위아래로 몇 줄을 더 읽을지 (메소드 문맥 확보용)

TARGET_EXTENSIONS = ('.sql', '.java', '.xml', '.py')

def run_command(*args) -> str:
    try:
        return subprocess.check_output(args, text=True).strip()
    except subprocess.CalledProcessError:
        return ""

def get_changed_files() -> List[str]:
    files = set()
    try:
        # HEAD^와 HEAD 사이의 변경된 파일 목록 추출
        diff_out = run_command("git", "diff", "--name-only", "HEAD^", "HEAD")
        files.update(diff_out.splitlines())
    except: pass
    
    if not files:
        for ext in TARGET_EXTENSIONS:
            files.update(glob.glob(f"**/*{ext}", recursive=True))

    return [f for f in files if f.endswith(TARGET_EXTENSIONS) and os.path.exists(f)]

def get_git_diff_ranges(file_path: str) -> List[Tuple[int, int]]:
    """
    git diff를 분석하여 변경된 라인 번호 범위(start, end)를 추출합니다.
    """
    ranges = []
    try:
        # 변경된 부분의 라인 정보만 가져옴 (-U0: 문맥 없이 라인 번호만)
        diff_out = run_command("git", "diff", "--unified=0", "HEAD^", "HEAD", "--", file_path)
        
        # @@ -old_start,old_count +new_start,new_count @@ 패턴 찾기
        for line in diff_out.splitlines():
            if line.startswith("@@"):
                match = re.search(r"\+(\d+)(?:,(\d+))?", line)
                if match:
                    start = int(match.group(1))
                    count = int(match.group(2)) if match.group(2) else 1
                    end = start + count - 1
                    ranges.append((start, end))
    except Exception as e:
        print(f"[Warn] Diff parsing failed for {file_path}: {e}")
    
    return ranges

def extract_relevant_chunks(file_path: str, content_lines: List[str]) -> str:
    """
    긴 파일의 경우, 변경된 라인 주변(Context)만 잘라서 합칩니다.
    """
    diff_ranges = get_git_diff_ranges(file_path)
    if not diff_ranges:
        return "" # 변경점 감지 실패 시 처리를 위해 빈 문자열 반환

    total_lines = len(content_lines)
    lines_to_keep = set()

    for start, end in diff_ranges:
        # 변경된 라인 위아래로 Padding만큼 더 가져옴 (메소드 문맥 확보)
        ctx_start = max(1, start - CONTEXT_PADDING)
        ctx_end = min(total_lines, end + CONTEXT_PADDING)
        
        for i in range(ctx_start, ctx_end + 1):
            lines_to_keep.add(i)

    if not lines_to_keep:
        return ""

    sorted_lines = sorted(list(lines_to_keep))
    
    chunks = []
    last_line = -1

    for line_num in sorted_lines:
        # 덩어리가 끊어지면 구분선 추가
        if last_line != -1 and line_num > last_line + 1:
            chunks.append("\n... (Skipped Unchanged Code) ...\n")
        
        chunks.append(content_lines[line_num - 1]) # 리스트 인덱스는 0부터 시작하므로 -1
        last_line = line_num

    return "\n".join(chunks)

def get_file_contents(path: str) -> List[str]:
    # 1. XML 처리 (MyBatis 등은 보통 짧거나 구조적이므로 전체 스캔 유지 권장)
    if path.endswith('.xml'):
        try:
            tree = ET.parse(path)
            sql_list = []
            for tag in ['select', 'insert', 'update', 'delete']:
                for el in tree.getroot().iter(tag):
                    if el.text:
                        clean_sql = mask_pii(el.text.strip())
                        sql_list.append(f"\n{clean_sql}")
            return sql_list
        except: return []
    
    # 2. Java, Python 등 소스 코드 처리
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 라인 단위로 분리
        lines = content.splitlines()
        
        # [Hybrid Scan Logic]
        # 파일이 작으면(300줄 미만) -> 전체 스캔 (Full Scan)
        if len(lines) <= MAX_FULL_SCAN_LINES:
            print(f"[sql-review] '{path}' is short ({len(lines)} lines). Performing Full Scan.")
            final_content = content
        else:
            # 파일이 크면 -> 변경된 부분 중심 스캔 (Smart Chunk Scan)
            print(f"[sql-review] '{path}' is long ({len(lines)} lines). Performing Diff Context Scan.")
            chunked_content = extract_relevant_chunks(path, lines)
            
            # Diff 추출 실패하거나 변경점이 없으면 안전하게 전체 스캔 (혹은 스킵)
            if not chunked_content:
                print(f"[Info] No specific diff ranges found or parsing failed. Fallback to Full Scan.")
                final_content = content
            else:
                final_content = chunked_content

        # PII 마스킹 후 반환
        masked_content = mask_pii(final_content)
        return [masked_content] if masked_content.strip() else []
            
    except Exception as e:
        print(f"[Error] Reading {path}: {e}")
        return []

# --- 아래부터는 기존 코드와 동일 (mask_pii, call_dify_workflow, is_rejected, main) ---
# (이전에 드린 mask_pii, call_dify_workflow, is_rejected 함수는 그대로 유지하세요)
# (특히 is_rejected 함수는 '상태: 반려' 정규식 쓰는 버전으로 꼭 유지하세요!)

# (이전 답변의 함수들을 여기에 붙여넣으세요)

def mask_pii(text: str) -> str:
    if not text: return text
    rrn_pattern = r'(?<!\d)(\d{6})[-\s]*([1-4]\d{6})(?!\d)'
    text = re.sub(rrn_pattern, r'\1-*******', text)
    phone_pattern = r'(01[016789])[-.\s]?(\d{3,4})[-.\s]?(\d{4})'
    text = re.sub(phone_pattern, r'\1-****-\3', text)
    email_pattern = r'([a-zA-Z0-9._%+-]+)(@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    text = re.sub(email_pattern, r'***\2', text)
    return text

def call_dify_workflow(content: str, file_name: str) -> str:
    url = f"{DIFY_API_BASE.rstrip('/')}/workflows/run"
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "inputs": {"sql_code": content, "file_name": file_name},
        "response_mode": "blocking",
        "user": "github-bot"
    }
    try:
        print(f"[sql-review] Sending {file_name} to Dify...")
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if not resp.ok: return f"❌ API 오류: {resp.status_code}"
        data = resp.json()
        outputs = data.get("data", {}).get("outputs", {})
        result = (outputs.get("text") or outputs.get("markdown_report") or outputs.get("result") or "")
        return str(result)
    except Exception as e: return f"❌ 연결 오류: {str(e)}"

def is_rejected(report_markdown: str) -> bool:
    if not report_markdown: return False
    status_pattern = r"(상태|Status)\s*[:\-]?\s*(.*)(반려|Fail|Reject|치명적인\s*오류)"
    match = re.search(status_pattern, report_markdown, re.IGNORECASE)
    if match: return True
    if "반려 (Reject)" in report_markdown or "Status: Reject" in report_markdown: return True
    return False

def main():
    target_files = get_changed_files()
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
            report_content.append(f"## 📄 `{fpath}`\n\n{res}\n\n---")
            if is_rejected(res): has_failure = True

    with open("sql_review_report.md", "w", encoding="utf-8") as f:
        status = "🚫 **반려된 코드가 있습니다.**" if has_failure else "✅ **모든 코드 통과**"
        f.write(f"# SQL Review Report\n\n### 전체 상태: {status}\n\n")
        if not report_content: f.write("검출된 코드가 없어 리포트가 비어있습니다.")
        else: f.write("\n".join(report_content))

    if has_failure: sys.exit(1)

if __name__ == "__main__":
    main()
