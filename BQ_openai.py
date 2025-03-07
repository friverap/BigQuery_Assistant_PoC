# /// script
# dependencies = [
#   "openai>=1.63.0",
#   "rich>=13.7.0",
#   "pydantic>=2.0.0",
#   "google-cloud-bigquery>=3.17.1",
#   "google-auth>=2.28.1",
#   "python-dotenv>=1.0.0",
# ]
# ///


import os
import sys
import json
import argparse
from typing import List
from rich.console import Console
from rich.panel import Panel
import openai
from pydantic import BaseModel, Field, ValidationError
from openai import pydantic_function_tool
from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize rich console
console = Console()

def normalize_table_path(table_name: str) -> str:
    """Normalize table path to use dots instead of colons.
    
    Args:
        table_name: The table name or path to normalize
        
    Returns:
        Normalized table path using dots
    """
    return table_name.replace(':', '.')

# Initialize BigQuery client
def init_bigquery_client(credentials_path: str):
    """Initialize BigQuery client with service account credentials."""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path
        )
        return bigquery.Client(credentials=credentials, project=credentials.project_id)
    except Exception as e:
        console.print(f"[red]Error initializing BigQuery client: {str(e)}[/red]")
        raise

def get_bigquery_config():
    """Get BigQuery configuration from environment variables.
    
    Returns:
        Tuple of (project_id, dataset_id, table_name)
    """
    project_id = os.getenv("BQ_PROJECT_ID")
    dataset_id = os.getenv("BQ_DATASET_ID")
    table_name = os.getenv("BQ_TABLE_NAME")
    
    if not all([project_id, dataset_id, table_name]):
        console.print(
            "[red]Error: BigQuery configuration not found in .env file[/red]"
        )
        console.print(
            "Please ensure your .env file contains BQ_PROJECT_ID, BQ_DATASET_ID, and BQ_TABLE_NAME"
        )
        sys.exit(1)
        
    return project_id, dataset_id, table_name

# Create our list of function tools from our pydantic models
class ListTablesArgs(BaseModel):
    reasoning: str = Field(
        ..., description="Explanation for listing tables relative to the user request"
    )


class DescribeTableArgs(BaseModel):
    reasoning: str = Field(..., description="Reason why the table schema is needed")
    table_name: str = Field(..., description="Name of the table to describe")


class SampleTableArgs(BaseModel):
    reasoning: str = Field(..., description="Explanation for sampling the table")
    table_name: str = Field(..., description="Name of the table to sample")
    row_sample_size: int = Field(
        ..., description="Number of rows to sample (aim for 3-5 rows)"
    )


class RunTestSQLQuery(BaseModel):
    reasoning: str = Field(..., description="Reason for testing this query")
    sql_query: str = Field(..., description="The SQL query to test")


class RunFinalSQLQuery(BaseModel):
    reasoning: str = Field(
        ...,
        description="Final explanation of how this query satisfies the user request",
    )
    sql_query: str = Field(..., description="The validated SQL query to run")


# Create tools list
tools = [
    pydantic_function_tool(ListTablesArgs),
    pydantic_function_tool(DescribeTableArgs),
    pydantic_function_tool(SampleTableArgs),
    pydantic_function_tool(RunTestSQLQuery),
    pydantic_function_tool(RunFinalSQLQuery),
]

table_name = get_bigquery_config()[2]
full_table_path = get_bigquery_config()[0] + "." + get_bigquery_config()[1] + "." + get_bigquery_config()[2]
AGENT_PROMPT = """<purpose>
    You are a world-class expert at crafting precise BigQuery SQL queries.
    Your goal is to generate accurate queries that exactly match the user's data needs.
    You will ALWAYS work with the table `{{full_table_path}}`.
    When writing queries, you MUST use the complete table path: `{{full_table_path}}`.
</purpose>

<instructions>
    <instruction>Use the provided tools to explore the database and construct the perfect query.</instruction>
    <instruction>Start by describing the '{{table_name}}' table to understand its schema and columns.</instruction>
    <instruction>Sample the '{{table_name}}' table to see actual data patterns.</instruction>
    <instruction>Test queries before finalizing them.</instruction>
    <instruction>Only call run_final_sql_query when you're confident the query is perfect.</instruction>
    <instruction>Be thorough but efficient with tool usage.</instruction>
    <instruction>If you find your run_test_sql_query tool call returns an error or won't satisfy the user request, try to fix the query or try a different query.</instruction>
    <instruction>Think step by step about what information you need.</instruction>
    <instruction>Be sure to specify every parameter for each tool call.</instruction>
    <instruction>Every tool call should have a reasoning parameter which gives you a place to explain why you are calling the tool.</instruction>
    <instruction>IMPORTANT: Always use the complete table path `{{full_table_path}}` in your queries.</instruction>
</instructions>

<tools>
    <tool>
        <name>list_tables</name>
        <description>Returns list of available tables in database</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Why we need to list tables relative to user request</description>
                <required>true</required>
            </parameter>
        </parameters>
    </tool>
    
    <tool>
        <name>describe_table</name>
        <description>Returns schema info for specified table (defaults to '{{table_name}}')</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Why we need to describe this table</description>
                <required>true</required>
            </parameter>
            <parameter>
                <name>table_name</name>
                <type>string</type>
                <description>Name of table to describe (defaults to '{{table_name}}')</description>
                <required>false</required>
            </parameter>
        </parameters>
    </tool>
    
    <tool>
        <name>sample_table</name>
        <description>Returns sample rows from specified table (defaults to '{{table_name}}')</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Why we need to sample this table</description>
                <required>true</required>
            </parameter>
            <parameter>
                <name>table_name</name>
                <type>string</type>
                <description>Name of table to sample (defaults to '{{table_name}}')</description>
                <required>false</required>
            </parameter>
            <parameter>
                <name>row_sample_size</name>
                <type>integer</type>
                <description>Number of rows to sample aim for 3-5 rows</description>
                <required>true</required>
            </parameter>
        </parameters>
    </tool>
    
    <tool>
        <name>run_test_sql_query</name>
        <description>Tests a SQL query and returns results (only visible to agent). Always use complete table path `{{full_table_path}}`.</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Why we're testing this specific query</description>
                <required>true</required>
            </parameter>
            <parameter>
                <name>sql_query</name>
                <type>string</type>
                <description>The SQL query to test (must use complete table path)</description>
                <required>true</required>
            </parameter>
        </parameters>
    </tool>
    
    <tool>
        <name>run_final_sql_query</name>
        <description>Runs the final validated SQL query and shows results to user. Always use complete table path `{{full_table_path}}`.</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Final explanation of how query satisfies user request</description>
                <required>true</required>
            </parameter>
            <parameter>
                <name>sql_query</name>
                <type>string</type>
                <description>The validated SQL query to run (must use complete table path)</description>
                <required>true</required>
            </parameter>
        </parameters>
    </tool>
</tools>

<user-request>
    {{user_request}}
</user-request>
"""


def list_tables(reasoning: str) -> List[str]:
    """Returns a list of tables in the BigQuery dataset.

    Args:
        reasoning: Explanation of why we're listing tables relative to user request

    Returns:
        List of table names as strings
    """
    try:
        dataset_ref = client.dataset(DATASET_ID)
        tables = list(client.list_tables(dataset_ref))
        table_names = [table.table_id for table in tables]
        console.log(f"[blue]List Tables Tool[/blue] - Reasoning: {reasoning}")
        return table_names
    except Exception as e:
        console.log(f"[red]Error listing tables: {str(e)}[/red]")
        return []


def describe_table(reasoning: str, table_name: str = table_name) -> str:
    """Returns schema information about the specified BigQuery table.

    Args:
        reasoning: Explanation of why we're describing this table
        table_name: Name of table to describe

    Returns:
        String containing table schema information
    """
    try:
        table_ref = client.dataset(DATASET_ID).table(table_name)
        table = client.get_table(table_ref)
        schema = table.schema
        output = "\n".join([f"{field.name}: {field.field_type}" for field in schema])
        console.log(f"[blue]Describe Table Tool[/blue] - Table: {table_name} - Reasoning: {reasoning}")
        return output
    except Exception as e:
        console.log(f"[red]Error describing table: {str(e)}[/red]")
        return ""


def sample_table(reasoning: str, table_name: str = table_name, row_sample_size: int = 5) -> str:
    """Returns a sample of rows from the specified BigQuery table.

    Args:
        reasoning: Explanation of why we're sampling this table
        table_name: Name of table to sample from 
        row_sample_size: Number of rows to sample aim for 3-5 rows

    Returns:
        String containing sample rows in readable format
    """
    try:
        # Normalize the table path to use dots
        table_name = normalize_table_path(table_name)
        
        # If table_name already contains the full path, use it directly
        if '.' in table_name:
            query = f"""
            SELECT *
            FROM `{table_name}`
            LIMIT {row_sample_size}
            """
        else:
            query = f"""
            SELECT *
            FROM `{PROJECT_ID}.{DATASET_ID}.{table_name}`
            LIMIT {row_sample_size}
            """
        query_job = client.query(query)
        results = query_job.result()
        rows = [dict(row.items()) for row in results]
        output = "\n".join([str(row) for row in rows])
        console.log(
            f"[blue]Sample Table Tool[/blue] - Table: {table_name} - Rows: {row_sample_size} - Reasoning: {reasoning}"
        )
        return output
    except Exception as e:
        console.log(f"[red]Error sampling table: {str(e)}[/red]")
        return ""


def run_test_sql_query(reasoning: str, sql_query: str) -> str:
    """Executes a test BigQuery query and returns results.

    Args:
        reasoning: Explanation of why we're running this test query
        sql_query: The SQL query to test

    Returns:
        Query results as a string
    """
    try:
        query_job = client.query(sql_query)
        results = query_job.result()
        rows = [dict(row.items()) for row in results]
        output = "\n".join([str(row) for row in rows])
        console.log(f"[blue]Test Query Tool[/blue] - Reasoning: {reasoning}")
        console.log(f"[dim]Query: {sql_query}[/dim]")
        return output
    except Exception as e:
        console.log(f"[red]Error running test query: {str(e)}[/red]")
        return str(e)


def run_final_sql_query(reasoning: str, sql_query: str) -> str:
    """Executes the final BigQuery query and returns results to user.

    Args:
        reasoning: Final explanation of how this query satisfies user request
        sql_query: The validated SQL query to run

    Returns:
        Query results as a string
    """
    try:
        query_job = client.query(sql_query)
        results = query_job.result()
        rows = [dict(row.items()) for row in results]
        output = "\n".join([str(row) for row in rows])
        console.log(
            Panel(
                f"[green]Final Query Tool[/green]\nReasoning: {reasoning}\nQuery: {sql_query}"
            )
        )
        return output
    except Exception as e:
        console.log(f"[red]Error running final query: {str(e)}[/red]")
        return str(e)


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="BigQuery Agent using OpenAI API")
    parser.add_argument(
        "-c", "--credentials", required=True, help="Path to Google Cloud credentials JSON file"
    )
    parser.add_argument("-p", "--prompt", required=True, help="The user's request")
    parser.add_argument(
        "-n",
        "--compute",
        type=int,
        default=10,
        help="Maximum number of agent loops (default: 10)",
    )
    args = parser.parse_args()

    # Configure the API key from .env file
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        console.print(
            "[red]Error: OPENAI_API_KEY not found in .env file[/red]"
        )
        console.print(
            "Please ensure your .env file contains the OPENAI_API_KEY variable"
        )
        sys.exit(1)

    openai.api_key = OPENAI_API_KEY

    # Set global variables for BigQuery
    global client, PROJECT_ID, DATASET_ID
    client = init_bigquery_client(args.credentials)
    PROJECT_ID, DATASET_ID, TABLE_NAME = get_bigquery_config()

    # Create a single combined prompt based on the full template
    completed_prompt = AGENT_PROMPT.replace("{{user_request}}", args.prompt)
    completed_prompt = completed_prompt.replace("{{full_table_path}}", full_table_path)
    completed_prompt = completed_prompt.replace("{{table_name}}", TABLE_NAME)
    messages = [{"role": "user", "content": completed_prompt}]

    compute_iterations = 0

    # Main agent loop
    while True:
        console.rule(
            f"[yellow]Agent Loop {compute_iterations+1}/{args.compute}[/yellow]"
        )
        compute_iterations += 1

        if compute_iterations >= args.compute:
            console.print(
                "[yellow]Warning: Reached maximum compute loops without final query[/yellow]"
            )
            raise Exception(
                f"Maximum compute loops reached: {compute_iterations}/{args.compute}"
            )

        try:
            # Generate content with tool support
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=tools,
                tool_choice="required",
            )

            if response.choices:
                assert len(response.choices) == 1
                message = response.choices[0].message

                if message.function_call:
                    func_call = message.function_call
                elif message.tool_calls and len(message.tool_calls) > 0:
                    tool_call = message.tool_calls[0]
                    func_call = tool_call.function
                else:
                    func_call = None

                if func_call:
                    func_name = func_call.name
                    func_args_str = func_call.arguments

                    messages.append(
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": tool_call.id,
                                    "type": "function",
                                    "function": func_call,
                                }
                            ],
                        }
                    )

                    console.print(
                        f"[blue]Function Call:[/blue] {func_name}({func_args_str})"
                    )
                    try:
                        # Validate and parse arguments using the corresponding pydantic model
                        if func_name == "ListTablesArgs":
                            args_parsed = ListTablesArgs.model_validate_json(
                                func_args_str
                            )
                            result = list_tables(reasoning=args_parsed.reasoning)
                        elif func_name == "DescribeTableArgs":
                            args_parsed = DescribeTableArgs.model_validate_json(
                                func_args_str
                            )
                            # If table_name is not provided, use default
                            table_name = args_parsed.table_name if hasattr(args_parsed, 'table_name') else "comercial"
                            result = describe_table(
                                reasoning=args_parsed.reasoning,
                                table_name=table_name,
                            )
                        elif func_name == "SampleTableArgs":
                            args_parsed = SampleTableArgs.model_validate_json(
                                func_args_str
                            )
                            # If table_name is not provided, use default
                            table_name = args_parsed.table_name if hasattr(args_parsed, 'table_name') else "comercial"
                            result = sample_table(
                                reasoning=args_parsed.reasoning,
                                table_name=table_name,
                                row_sample_size=args_parsed.row_sample_size,
                            )
                        elif func_name == "RunTestSQLQuery":
                            args_parsed = RunTestSQLQuery.model_validate_json(
                                func_args_str
                            )
                            result = run_test_sql_query(
                                reasoning=args_parsed.reasoning,
                                sql_query=args_parsed.sql_query,
                            )
                        elif func_name == "RunFinalSQLQuery":
                            args_parsed = RunFinalSQLQuery.model_validate_json(
                                func_args_str
                            )
                            result = run_final_sql_query(
                                reasoning=args_parsed.reasoning,
                                sql_query=args_parsed.sql_query,
                            )
                            console.print("\n[green]Final Results:[/green]")
                            console.print(result)
                            return
                        else:
                            raise Exception(f"Unknown tool call: {func_name}")

                        console.print(
                            f"[blue]Function Call Result:[/blue] {func_name}(...) ->\n{result}"
                        )

                        # Append the function call result into our messages as a tool response
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({"result": str(result)}),
                            }
                        )

                    except Exception as e:
                        error_msg = f"Argument validation failed for {func_name}: {e}"
                        console.print(f"[red]{error_msg}[/red]")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({"error": error_msg}),
                            }
                        )
                        continue
                else:
                    raise Exception(
                        "No function call in this response - should never happen"
                    )

        except Exception as e:
            console.print(f"[red]Error in agent loop: {str(e)}[/red]")
            raise e


if __name__ == "__main__":
    main()