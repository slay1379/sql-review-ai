import os
import subprocess
import json
import textwrap
import subprocess

import requests


API_URL = os.getenv("SQL_REVIEW_API_URL", "http://localhost:8000/lint")


def run(*args) -> str:
    """git 명령어 래퍼 (이미 있다면 기존 거 써도 됨)"""
    return subprocess.check_output(args, text=True)


def get_changed_files() -> list[str]:
    """
    변경된 SQL 파일 목록을 리턴한다.

    1) 보통은 HEAD^..HEAD diff 로 변경 파일만 가져옴
    2) 첫 커밋이거나 HEAD^ 가 없어서 실패하면,
       전체 트래킹 파일 목록에서 *.sql 만 가져오도록 fallback
    """
    try:
        # 일반적인 케이스: 직전 커밋과 비교
        out = run("git", "diff", "--name-only", "HEAD^", "HEAD")
        files = [f for f in out.splitlines() if f.endswith(".sql")]
        if files:
            return files
    except subprocess.CalledProcessError:
        # HEAD^ 가 없거나 할 때 여기로 떨어짐
        pass

    # 👉 fallback: 레포 전체에서 *.sql
    out = run("git", "ls-files")
    files = [f for f in out.splitlines() if f.endswith(".sql")]
    return files


def extract_sql_from_file(path: str) -> list[str]:
    """
    파일에서 SQL 추출 (간단 버전)
    - .sql  : 파일 전체
    - .py   : triple-quote 안에 있는 문자열 중 SELECT/INSERT/UPDATE/DELETE 포함
    - .js/.ts : `, ", ` 안의 SQL 비슷한 문자열
    """
    sql_list: list[str] = []
    if not os.path.exists(path):
        return sql_list

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if path.endswith(".sql"):
        sql_list.append(text)
        return sql_list

    # 아주 단순한 패턴 기반: "SELECT", "INSERT" 등 들어간 긴 줄들 모으기
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
    resp = requests.post(API_URL, json=payload, timeout=30)

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


def main() -> None:
    changed_files = get_changed_files()
    target_files = [
        f
        for f in changed_files
        if f.endswith((".sql", ".py", ".js", ".ts"))
    ]

    if not target_files:
        print("[sql-review] SQL 관련 변경 파일 없음. 통과.")
        return

    print(f"[sql-review] SQL 후보 파일: {target_files}")

    problems: list[str] = []

    for path in target_files:
        sql_candidates = extract_sql_from_file(path)
        if not sql_candidates:
            continue

        for idx, sql in enumerate(sql_candidates, start=1):
            print(f"[sql-review] ---- {path} (snippet #{idx}) ----")
            print(textwrap.indent(sql[:400], prefix="    "))

            result = call_sqlfluff_api(sql)

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

    if problems:
        print("\n[sql-review] =======================")
        print("[sql-review] ❌ SQL 리뷰 실패: 문제 발견")
        print("[sql-review] =======================\n")
        for p in problems:
            print(p)
            print("\n---------------------------\n")
        raise SystemExit(1)

    print("[sql-review] ✅ 모든 SQL이 검사를 통과했습니다.")


if __name__ == "__main__":
    main()
