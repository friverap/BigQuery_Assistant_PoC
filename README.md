# BigQuery SQL Query Assistant

A powerful AI-powered tool that helps you interact with BigQuery using natural language. This tool uses OpenAI's GPT-4 model to understand your requests and generate accurate SQL queries for BigQuery.

## Features

- Natural language to SQL query conversion
- Interactive query refinement
- Schema exploration
- Data sampling
- Query testing and validation
- Secure credential management
- Rich console output

## Prerequisites

- Python 3.11 or higher
- Google Cloud Service Account with BigQuery access
- OpenAI API key
- Required Python packages (see dependencies)

## Configuration

1. Create a `.env` file in the project root with the following variables:
```bash
OPENAI_API_KEY=your_openai_api_key
BQ_PROJECT_ID=projenct-id
BQ_DATASET_ID=dataset_id
BQ_TABLE_NAME=table_name
```

2. Place your Google Cloud service account credentials JSON file in a secure location

## Usage
Install uv:
```bash
pip install uv
```
Run the script with the following command:
```bash
uv run BQ_openai.py -c path/to/credentials.json -p "your query request" [-n max_compute_loops]
```
All dependencies will be installed automatically.

Arguments:
- `-c, --credentials`: Path to Google Cloud credentials JSON file
- `-p, --prompt`: Your natural language query request
- `-n, --compute`: Maximum number of agent loops (default: 10)

## Features

The tool provides several capabilities:
- List available tables
- Describe table schemas
- Sample table data
- Test SQL queries
- Execute final validated queries

## Security

- Credentials are managed through environment variables
- Service account authentication for BigQuery
- No hardcoded sensitive information
- Secure credential handling

## Example Usage

```bash
uv run BQ_openai.py -c credentials.json -p "Show me the 3 top users (nom_cliente) with the highest tons ordered (toneladas_pedidas) in the last 3 months"
```

## Error Handling

The tool includes comprehensive error handling for:
- Missing credentials
- Invalid configurations
- Query execution errors
- API communication issues

## Notes

- Always uses the complete table path: `{PROJECT_ID}.{DATASET_ID}.{table_name}`
- Automatically normalizes table paths
- Provides detailed logging and feedback
- Interactive query refinement process

## Contributing

Feel free to submit issues and enhancement requests! 
