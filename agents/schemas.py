from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Any, Dict
from datetime import datetime


# =========================================================
# -------- Query analyzer node schemas -------
# =========================================================

# class UserQuery(BaseModel):
#     raw_query: str = Field(
#         description="Original natural language query from the user"
#     )
#     received_at: Optional[datetime] = None


class QueryAnalysis(BaseModel):
    # ---------- Query Understanding ----------
    intent: Literal[
        "extreme_value",
        "average",
        "minimum",
        "latest_value",
        "comparison",
        "trend",
        "distance_based",
        "time_based",
        "summary",
        "unknown"
    ] = Field(
        description="Primary intent detected from the user query"
    )

    # ---------- Data Needed ----------
    telemetry_fields_needed: List[str] = Field(
        description="Telemetry fields/sensors needed to answer the question, e.g. rpm, throttle, speed"
    )

    analysis_operations: List[
        Literal[
            "max",
            "min",
            "avg",
            "sum",
            "count",
            "latest",
            "difference",
            "distance_at_event",
            "time_at_event",
            "correlation",
            "unknown"
        ]
    ] = Field(
        description="Operations required on the telemetry fields"
    )

    # ---------- Optional Constraints ----------
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional filter conditions inferred from the query"
    )

    time_range_hint: Optional[str] = Field(
        default=None,
        description="Natural language or parsed time range hint if present"
    )

    lap_hint: Optional[str] = Field(
        default=None,
        description="Optional lap/session hint if present"
    )

    # ---------- Reasoning ----------
    reasoning: str = Field(
        description="Short reasoning for why these fields and operations are needed"
    )

    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence of the analyzer node"
    )


# =========================================================
# -------- SQL generator node schemas -------
# =========================================================

# =========================================================
# -------- SQL generator node schemas -------
# =========================================================

class SQLQueryPayload(BaseModel):
    sql: str = Field(
        description="Parameterized SQL query string to send to the backend DB API"
    )
    params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Named parameters for the SQL query"
    )
    max_rows: Optional[int] = Field(
        default=None,
        description="Maximum number of rows to return"
    )

class SQLQuery(BaseModel):
    # ---------- Identification ----------
    query_name: str = Field(
        description="Unique logical name for the SQL query"
    )

    purpose: str = Field(
        description="Why this query is needed to answer the user question"
    )

    # ---------- SQL API Payload ----------
    sql: SQLQueryPayload = Field(
        description="JSON payload that will be sent directly to the backend DB API"
    )

class SQLGeneration(BaseModel):
    # ---------- Input Context ----------
    original_query: str = Field(
        description="Original user query"
    )

    telemetry_fields_needed: List[str] = Field(
        description="Telemetry fields passed from analyzer"
    )

    analysis_operations: List[Literal[
        "max",
        "min",
        "avg",
        "sum",
        "count",
        "latest",
        "difference",
        "distance_at_event",
        "time_at_event",
        "correlation",
        "unknown"
    ]] = Field(
        description="Operations passed from analyzer"
    )

    # ---------- Generated Queries ----------
    sql_queries: List[SQLQuery] = Field(
        description="List of SQL queries generated for the DB runner"
    )

    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence of SQL generation node"
    )

# =========================================================
# -------- Query runner / data getter node schemas -------
# =========================================================

class QueryExecutionResult(BaseModel):
    # ---------- Identification ----------
    query_name: str
    purpose: str

    # ---------- SQL ----------
    sql: SQLQueryPayload

    # ---------- Execution Status ----------
    success: bool
    execution_time_ms: Optional[float] = None
    row_count: Optional[int] = None

    # ---------- Results ----------
    result_json: Optional[Any] = Field(
        default=None,
        description="Raw JSON output returned from backend API for this SQL query"
    )

    # ---------- Error ----------
    error_message: Optional[str] = None


class DataGetterOutput(BaseModel):
    # ---------- Results ----------
    query_results: List[QueryExecutionResult] = Field(
        description="Execution results for all generated SQL queries"
    )

    # ---------- Aggregate Stats ----------
    total_queries: int
    successful_queries: int
    failed_queries: int
    total_execution_time_ms: Optional[float] = None

    # ---------- Metadata ----------
    generated_at: Optional[datetime] = None


# =========================================================
# -------- Final aggregator / analysis node schemas -------
# =========================================================

class FinalAnswer(BaseModel):
    # ---------- User-facing Output ----------
    answer_text: str = Field(
        description="Final natural language answer to the user query"
    )

    short_answer: Optional[str] = Field(
        default=None,
        description="Optional concise answer for UI display"
    )

    # ---------- Structured Support ----------
    supporting_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="Relevant structured supporting data extracted from query outputs"
    )

    # ---------- Reasoning ----------
    reasoning: str = Field(
        description="Short explanation of how the answer was derived"
    )

    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence of final answer"
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings such as missing data, partial failures, or ambiguity"
    )

    generated_at: datetime


# =========================================================
# -------- Logging schemas -------
# =========================================================

# class SystemLogEntry(BaseModel):
#     timestamp: datetime
#     node_name: Literal[
#         "query_analyzer",
#         "sql_generator",
#         "query_runner",
#         "final_aggregator",
#         "system"
#     ]
#     status: Literal["started", "completed", "failed", "checkpoint"]
#     message: str
#     details: Optional[Dict[str, Any]] = None


# class ErrorLogEntry(BaseModel):
#     timestamp: datetime
#     node_name: Literal[
#         "query_analyzer",
#         "sql_generator",
#         "query_runner",
#         "final_aggregator",
#         "system"
#     ]
#     error_type: str
#     error_message: str
#     details: Optional[Dict[str, Any]] = None


# class PostgresLogEntry(BaseModel):
#     timestamp: datetime
#     query_name: str
#     sql: str
#     success: bool
#     execution_time_ms: Optional[float] = None
#     row_count: Optional[int] = None
#     result_preview: Optional[Any] = None
#     error_message: Optional[str] = None


# =========================================================
# -------- Main workflow state schema -------
# =========================================================

class AgentWorkflowState(BaseModel):
    # ---------- Original Input ----------
    #user_query: UserQuery
    query: str

    # ---------- Node Outputs ----------
    query_analysis: Optional[QueryAnalysis] = None
    sql_generation: Optional[SQLGeneration] = None
    data_getter_output: Optional[DataGetterOutput] = None
    final_answer: Optional[FinalAnswer] = None

    # ---------- Logs ----------
    # system_logs: List[SystemLogEntry] = Field(default_factory=list)
    # error_logs: List[ErrorLogEntry] = Field(default_factory=list)
    # postgres_logs: List[PostgresLogEntry] = Field(default_factory=list)

    # ---------- Request Metadata ----------
    request_id: Optional[str] = None
    session_id: Optional[str] = None