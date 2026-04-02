import re
import sqlparse

BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
    "ALTER", "CREATE", "GRANT", "REVOKE", "EXECUTE", "EXEC", "ATTACH"
}


class ValidationError(Exception):
    pass


def validate_sql(sql: str) -> str:
    if not sql or not sql.strip():
        raise ValidationError("Empty SQL query.")

    # Strip markdown fences
    sql = re.sub(r"```sql|```", "", sql, flags=re.IGNORECASE).strip()

    parsed = sqlparse.parse(sql)[0]
    stmt_type = parsed.get_type()

    if stmt_type != "SELECT":
        raise ValidationError(f"Only SELECT queries are allowed. Got: {stmt_type or 'unknown'}.")

    sql_upper = sql.upper()
    for keyword in BLOCKED_KEYWORDS:
        if re.search(r'\b' + keyword + r'\b', sql_upper):
            raise ValidationError(f"Blocked keyword detected: {keyword}")

    if re.search(r'\bsqlite_\w+\b', sql, re.IGNORECASE):
        raise ValidationError("Access to SQLite system tables is not allowed.")

    # Add LIMIT if missing
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";").rstrip() + "\nLIMIT 200;"
    else:
        sql = re.sub(
            r'\bLIMIT\s+(\d+)',
            lambda m: f"LIMIT {min(int(m.group(1)), 500)}",
            sql, flags=re.IGNORECASE
        )

    return sql.strip()
