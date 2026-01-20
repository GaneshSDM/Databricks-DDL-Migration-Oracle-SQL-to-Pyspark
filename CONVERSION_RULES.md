# Oracle → Databricks SQL Conversion - Output Rules

## STRICT OUTPUT REQUIREMENTS

The system is configured to output **ONLY executable Databricks SQL** with NO explanations, markdown, or "Changes and Enhancements" sections.

## Code Changes Made

### 1. ai_migration.py
- **Import**: Added `import re` for regex cleanup operations
- **_clean_model_output()**: Enhanced to remove all non-SQL content:
  - Strips markdown code fences (```sql)
  - Removes "### Changes and Enhancements" sections
  - Filters out explanation patterns starting with ** or containing keywords like "Input/Output"
- **migrate_schema()**: Prompts explicitly state "Return ONLY Databricks SQL"
- **_process_large_sql()**: Modified combined results to return only SQL, stripping changes sections
- **migrate_procedure()**: Updated prompt to exclude "Changes and Enhancements" requirement
- **optimize_query()**: Updated prompt to return only optimized SQL

### 2. batch_converter.py
- **convert_file()**: Added cleanup logic to:
  - Strip "### Changes and Enhancements" sections
  - Remove markdown code fences
  - Return only raw SQL code

### 3. app.py
- **Output Display**: Modified tabs to show only "Converted SQL" (removed "Changes & Enhancements" tab)
- **SQL Extraction**: Enhanced logic to:
  - Remove markdown code fences
  - Strip "Changes and Enhancements" sections before display
  - Handle validation and test case tabs with correct indexing

## Prompt Changes

All LLM prompts now include explicit instructions:
```
Return ONLY Databricks SQL.
Do NOT include explanations, markdown (```sql), or "Changes and Enhancements" sections.
```

## Result Processing

Multiple layers ensure no explanatory content reaches output:
1. **LLM Level**: Prompts explicitly forbid explanations
2. **Cleaning Level**: _clean_model_output() strips markdown and sections
3. **Batch Level**: convert_file() removes any remaining sections
4. **UI Level**: app.py filters before display

## Data Type Conversion Rules (Applied Silently)

- Oracle NUMBER → INT or DECIMAL(p,s)
- Oracle VARCHAR2 → VARCHAR
- Oracle NCHAR/NVARCHAR2 → CHAR/VARCHAR
- Oracle TIMESTAMP variants → TIMESTAMP
- Oracle CLOB → STRING
- Oracle BLOB/RAW/LONG RAW → BINARY
- Oracle INTERVAL types → STRING
- All CREATE TABLE statements include USING DELTA
- Remove double-quoted identifiers
- Remove Oracle-specific constraints from CREATE TABLE body (move CHECK/UNIQUE to ALTER TABLE)

## Output Format (STRICT)

✅ **VALID** - Only SQL:
```sql
CREATE TABLE ALL_ORACLE_DATATYPES_DEMO (
    COL_NUMBER INT,
    COL_VARCHAR2 VARCHAR(100)
)
USING DELTA;
```

❌ **INVALID** - Any non-SQL content:
```sql
### Changes and Enhancements
- Converted NUMBER to INT
```
