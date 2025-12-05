import os
import subprocess
import json
import textwrap
from typing import List, Dict, Any

import requests

# GitHub Actions 에서 env 로 넘겨주는 API URL (없으면 localhost 기본값)
API_URL = os.getenv("SQL_REVIEW_API_URL", "http://localhost:8000/lint")


def run(*args: str) -> str:
    """git 명령 래퍼"""
    return subprocess.check_output(args, text=True)


def get_changed_files() -> List[str]:
    """
    변경된 파일 목록 가져오기
    1) HEAD^..HEAD 기준 diff
    2) 실패하면 전체 ls-files 에서 *.sql, *.py, *.js, *.ts
    """
    try:
        out = run("git", "diff", "--name-only", "HEAD^", "HEAD")
        files = [f for f in out.splitlines() if f.endswith((".sql", ".py", ".js", ".ts"))]
        if files:
            return files
    except subprocess.CalledProcessError:
        pass

    out = run("git", "ls-files")
    files = [f for f in out.splitlines() if f.endswith((".sql", ".py", ".js", ".ts"))]
    return files


def extract_sql_from_file(path: str) -> List[str]:
    """
    파일에서 SQL 후보 추출
    - .sql : 전체 내용
    - 그 외 : SELECT / INSERT / UPDATE / DELETE / MERGE 가 들어간 라인들을 묶어서 하나의 스니펫으로
    """
    sql_list: List[str] = []
    if not os.path.exists(path):
        return sql_list

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if path.endswith(".sql"):
        sql_list.append(text)
        return sql_list

    candidates: List[str] = []
    for line in text.splitlines():
        line_stripped = line.strip()
        if any(
            kw in line_stripped.upper()
            for kw in ["SELECT ", "INSERT ", "UPDATE ", "DELETE ", "MERGE "]
        ):
            candidates.append(line_stripped)

    if candidates:
        sql_list.append("\n".join(candidates))

    return sql_list


def call_sqlfluff_api(sql: str) -> Dict[str, Any]:
    """FastAPI /lint 호출"""
    payload = {"sql": sql, "dialect": "ansi"}
    print(f"[sql-review] call API: {API_URL}")
    resp = requests.post(API_URL, json=payload, timeout=15)

    # 고위험 쿼리는 400 + status=blocked 로 떨어짐
    if resp.status_code == 400:
        try:
            detail = resp.json().get("detail", {})
        except Exception:
            detail = {"raw": resp.text}
        return {"blocked": True, "detail": detail}

    resp.raise_for_status()
    data = resp.json()
    return {"blocked": False, "detail": data}


def build_markdown_report(results: List[Dict[str, Any]]) -> str:
    """
    GitHub PR 코멘트용 Markdown 리포트 생성
    results: 각 스니펫별 검사 결과 리스트
    """
    lines: List[str] = []
    lines.append("## SQL Review Report")
    lines.append("")
    if not results:
        lines.append("검사할 SQL 변경사항이 없습니다. ✅")
        return "\n".join(lines)

    overall_fail = any(r["has_problem"] for r in results)
    lines.append(f"- 전체 상태: {'❌ 문제 발견' if overall_fail else '✅ 모든 SQL 통과'}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for r in results:
        lines.append(f"### 📄 파일: `{r['path']}` (snippet #{r['snippet']})")
        lines.append("")
        lines.append(f"- 차단 여부(blocked): **{r['blocked']}**")
        lines.append(f"- 보안 최대 위험도(max_severity): **{r['max_severity']}**")
        lines.append("")
        if r["blocked"]:
            lines.append("**🚫 고위험 SQL 차단 상세**")
            lines.append("```json")
            lines.append(json.dumps(r["raw_detail"], ensure_ascii=False, indent=2))
            lines.append("```")
        else:
            sec = r["security"]
            syn = r["syntax"]
            lines.append("**🛡 Security analysis**")
            lines.append("```json")
            lines.append(json.dumps(sec, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
            lines.append("**🧩 Syntax / Lint analysis**")
            lines.append("```json")
            lines.append(json.dumps(syn, ensure_ascii=False, indent=2))
            lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    changed_files = get_changed_files()
    target_files = [
        f for f in changed_files if f.endswith((".sql", ".py", ".js", ".ts"))
    ]

    if not target_files:
        print("[sql-review] SQL 관련 변경 파일 없음. 통과.")
        # 그래도 리포트 파일은 만들어 둔다.
        report = "## SQL Review Report\n\n검사할 SQL 변경사항이 없습니다. ✅\n"
        with open("sql_review_report.md", "w", encoding="utf-8") as f:
            f.write(report)
        return

    print(f"[sql-review] SQL 후보 파일: {target_files}")

    problems: List[str] = []
    report_items: List[Dict[str, Any]] = []

    for path in target_files:
        sql_candidates = extract_sql_from_file(path)
        if not sql_candidates:
            continue

        for idx, sql in enumerate(sql_candidates, start=1):
            print(f"[sql-review] ---- {path} (snippet #{idx}) ----")
            print(textwrap.indent(sql[:400], prefix="    "))

            result = call_sqlfluff_api(sql)

            entry: Dict[str, Any] = {
                "path": path,
                "snippet": idx,
                "blocked": False,
                "has_problem": False,
                "max_severity": "",
                "security": {},
                "syntax": {},
                "raw_detail": result["detail"],
            }

            if result["blocked"]:
                entry["blocked"] = True
                entry["has_problem"] = True
                entry["max_severity"] = "high"
                problems.append(f"{path} (snippet #{idx}) : BLOCKED")
            else:
                data = result["detail"]
                security = data.get("security_analysis", {})
                syntax = data.get("syntax_analysis", {})
                entry["security"] = security
                entry["syntax"] = syntax
                entry["max_severity"] = security.get("max_severity", "unknown")

                if security.get("max_severity") == "high":
                    entry["has_problem"] = True
                    problems.append(f"{path} (snippet #{idx}) : 보안 위험도 HIGH")

                if syntax.get("found_errors"):
                    entry["has_problem"] = True
                    problems.append(f"{path} (snippet #{idx}) : SQL 문법/스타일 오류")

            report_items.append(entry)

    # Markdown 리포트 생성 & 파일로 저장
    report_md = build_markdown_report(report_items)
    with open("sql_review_report.md", "w", encoding="utf-8") as f:
        f.write(report_md)

    if problems:
        print("\n[sql-review] =======================")
        print("[sql-review] ❌ SQL 리뷰 실패: 문제 발견")
        print("[sql-review] =======================\n")
        for p in problems:
            print(p)
        # 실패로 처리해서 PR 체크는 빨간불
        raise SystemExit(1)

    print("[sql-review] ✅ 모든 SQL이 검사를 통과했습니다.")


if __name__ == "__main__":
    main()
