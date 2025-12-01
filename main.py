from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import tempfile
import os
import json
import re

app = FastAPI()

# -----------------------------
# 요청 모델
# -----------------------------
class SQLRequest(BaseModel):
    sql: str
    dialect: str = "ansi"

# -----------------------------
# 1) 보안 검사 (Deterministic Layer)
# -----------------------------
def check_security(sql: str):
    warnings = []
    max_severity = "low"

    # High severity
    dangerous_keywords = ["DROP", "TRUNCATE", "DELETE", "ALTER", "GRANT"]
    for word in dangerous_keywords:
        if re.search(rf"\b{word}\b", sql, re.IGNORECASE):
            warnings.append(f"⛔ 고위험 명령어 감지!: {word}")
            max_severity = "high"

    # Medium severity
    if re.search(r"SELECT\s+\*", sql, re.IGNORECASE):
        warnings.append("⚠️ 성능/보안 경고: SELECT * 사용 (컬럼 명시 권장)")
        if max_severity == "low":
            max_severity = "medium"

    # PII 감지
    if re.search(r"\d{6}[-]\d{7}", sql):
        warnings.append("🛡️ 개인정보(PII) 노출 의심: 주민등록번호 패턴")
        if max_severity == "low":
            max_severity = "medium"

    return {
        "is_safe": max_severity != "high",
        "warnings": warnings,
        "max_severity": max_severity
    }

# -----------------------------
# 2) Lint API
# -----------------------------
@app.post("/lint")
async def lint_sql(request: SQLRequest):
    security_result = check_security(request.sql)
    
    temp_file_path = None # finally에서 참조하기 위해 초기화

    try:
        # -----------------------------
        # (B) SQL 파일 생성 (Safe Write)
        # -----------------------------
        # delete=False로 만들고, with 블록 밖에서 subprocess 실행
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".sql", delete=False, encoding='utf-8') as tmp:
            tmp.write(request.sql)
            temp_file_path = tmp.name
            # 파일이 닫히면서(with 종료) 데이터가 디스크에 확실히 저장됨

        # -----------------------------
        # (C) SQLFluff 실행
        # -----------------------------
        result = subprocess.run(
            ["sqlfluff", "lint", temp_file_path, "--dialect", request.dialect, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8' # 인코딩 명시
        )

        if result.returncode not in (0, 1):
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "Linter process failed",
                    "stderr": result.stderr,
                }
            )

        # -----------------------------
        # (D) JSON 파싱
        # -----------------------------
        try:
            raw_json = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
             raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "message": "Failed to parse linter JSON output",
                    "raw_output": result.stdout
                }
            )

        # -----------------------------
        # (E) 결과 정제
        # -----------------------------
        simplified_errors = []
        for file_result in raw_json:
            violations = file_result.get("violations", [])
            for v in violations:
                simplified_errors.append(
                    f"Line {v.get('line_no', '?')}: {v.get('description', 'Unknown')} (Code: {v.get('code', 'N/A')})"
                )

        return {
            "status": "success",
            "security_analysis": security_result,
            "syntax_analysis": {
                "found_errors": len(simplified_errors) > 0,
                "details": simplified_errors
            }
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Linting process timed out (10s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # (F) 파일 정리
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
