import os
import subprocess
import json
import textwrap
import requests

API_URL = os.environ["SQL_REVIEW_API_URL"]


def run(*args) -> str:
    """git 명령어 래퍼"""
    return subprocess.check_output(args, text=True)


def get_changed_files() -> list[str]:
    """
    변경된 SQL 관련 파일 목록을 리턴한다.

    1) 기본: HEAD^..HEAD diff 기준
    2) 첫 커밋 등으로 HEAD^가 없으면 레포 전체에서 *.sql만 대상
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


def extract_sql_from_file(path: str) -> list[str]:
    """
    파일에서 SQL 추출 (간단 버전)
    - .sql: 파일 전체
    - .py/.js/.ts: SELECT/INSERT/UPDATE/DELETE 포함된 줄만 모아서 하나의 snippet으로
    """
    sql_list: list[str] = []
    if not os.path.exists(path):
        return sql_list

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if path.endswith(".sql"):
        sql_list.append(text)
        return sql_list

    candidates = []
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


def call_sqlfluff_api(sql: str) -> dict:
    """FastAPI /lint 호출."""
    payload = {"sql": sql, "dialect": "ansi"}
    print(f"[sql-review] call API: {API_URL}")
    resp = requests.post(API_URL, json=payload, timeout=10)

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


def build_markdown_for_snippet(path: str, idx: int, sql: str, result: dict) -> str:
    """
    각 파일/스니펫에 대한 Markdown 리포트 조각 생성.
    나중에 이걸 전부 합쳐서 sql_review_report.md로 저장한다.
    """
    header = f"## 파일: `{path}` (snippet #{idx})\n"

    # 고위험 차단 케이스
    if result["blocked"]:
        detail = result.get("detail", {})
        sec = detail.get("security_analysis", {})
        warnings = sec.get("warnings", [])

        body = [
            "**상태:** 🚫 고위험 SQL 차단 (status=blocked)",
            "",
            "**차단 사유:**",
        ]
        if warnings:
            for w in warnings:
                body.append(f"- {w}")
        else:
            body.append("- 상세 경고 정보 없음")

        body.append("")
        body.append("```sql")
        body.append(sql.strip()[:400])
        body.append("```")
        body.append("")
        body.append("```json")
        body.append(json.dumps(detail, ensure_ascii=False, indent=2))
        body.append("```")

        return header + "\n".join(body) + "\n\n---\n\n"

    # 정상 / 경고 케이스
    data = result["detail"]
    sec = data.get("security_analysis", {})
    syntax = data.get("syntax_analysis", {})

    max_severity = sec.get("max_severity", "low")
    warnings = sec.get("warnings", [])
    has_pii = sec.get("has_pii", False)

    found_errors = syntax.get("found_errors", False)
    syntax_details = syntax.get("details", [])

    status = "✅ 통과"
    if max_severity == "high" or found_errors:
        status = "⚠️ 조치 필요"

    lines: list[str] = []
    lines.append(header)
    lines.append(f"**상태:** {status}")
    lines.append("")
    lines.append("### 1. 보안 분석 결과")
    lines.append(f"- 최대 위험도: **{max_severity}**")
    lines.append(f"- PII 감지 여부: **{has_pii}**")
    if warnings:
        lines.append("- 경고 목록:")
        for w in warnings:
            lines.append(f"  - {w}")
    else:
        lines.append("- 경고 없음")

    lines.append("")
    lines.append("### 2. Linter / 문법 분석 결과")
    if found_errors and syntax_details:
        lines.append("- 발견된 오류:")
        for d in syntax_details:
            lines.append(f"  - {d}")
    else:
        lines.append("- 문법/스타일 오류 없음")

    lines.append("")
    lines.append("### 3. 검사 대상 SQL 스니펫")
    lines.append("```sql")
    lines.append(sql.strip()[:400])
    lines.append("```")

    lines.append("\n---\n")
    return "\n".join(lines) + "\n"


def main() -> None:
    changed_files = get_changed_files()
    target_files = [
        f for f in changed_files if f.endswith((".sql", ".py", ".js", ".ts"))
    ]

    if not target_files:
        print("[sql-review] SQL 관련 변경 파일 없음. 통과.")
        # 빈 리포트라도 생성해두면 Summary에서 보기 편함
        with open("sql_review_report.md", "w", encoding="utf-8") as fw:
            fw.write("# SQL Review Report\n\n변경된 SQL 관련 파일이 없습니다.\n")
        return

    print(f"[sql-review] SQL 후보 파일: {target_files}")

    problems: list[str] = []
    markdown_parts: list[str] = []
    markdown_parts.append("# SQL Review Report\n")

    for path in target_files:
        sql_candidates = extract_sql_from_file(path)
        if not sql_candidates:
            continue

        for idx, sql in enumerate(sql_candidates, start=1):
            print(f"[sql-review] ---- {path} (snippet #{idx}) ----")
            print(textwrap.indent(sql[:400], prefix="    "))

            result = call_sqlfluff_api(sql)

            # Markdown 조각 생성
            snippet_md = build_markdown_for_snippet(path, idx, sql, result)
            markdown_parts.append(snippet_md)

            if result["blocked"]:
                detail = result["detail"]
                msg = textwrap.dedent(
                    f"""
                    파일: {path} (snippet #{idx})
                    결과: 🚫 고위험 SQL 차단 (status=blocked)

                    detail:
                    {json.dumps(detail, ensure_ascii=False, indent=2)}
                    """
                )
                problems.append(msg)
                continue

            data = result["detail"]
            security = data.get("security_analysis", {})
            syntax = data.get("syntax_analysis", {})

            if security.get("max_severity") == "high":
                msg = textwrap.dedent(
                    f"""
                    파일: {path} (snippet #{idx})
                    결과: 🚨 보안 위험도 HIGH

                    security_analysis:
                    {json.dumps(security, ensure_ascii=False, indent=2)}
                    """
                )
                problems.append(msg)

            if syntax.get("found_errors"):
                msg = textwrap.dedent(
                    f"""
                    파일: {path} (snippet #{idx})
                    결과: ⚠️ SQL 문법/스타일 오류 발견

                    syntax_analysis:
                    {json.dumps(syntax, ensure_ascii=False, indent=2)}
                    """
                )
                problems.append(msg)

    # 🔥 여기서 최종 Markdown 파일로 저장
    report_text = "\n".join(markdown_parts)
    with open("sql_review_report.md", "w", encoding="utf-8") as fw:
        fw.write(report_text)

    if problems:
        print("\n[sql-review] =======================")
        print("[sql-review] ❌ SQL 리뷰 실패: 문제 발견")
        print("[sql-review] =======================\n")
        for p in problems:
            print(p)
            print("\n---------------------------\n")
        # 실패 시에도 리포트는 이미 파일로 남아 있음
        raise SystemExit(1)

    print("[sql-review] ✅ 모든 SQL이 검사를 통과했습니다.")


if __name__ == "__main__":
    main()
