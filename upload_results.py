import requests
import json
import sys
import os

# Hardcoded API endpoint from your provided URL
API_ENDPOINT = "https://otobspxsek.execute-api.us-east-1.amazonaws.com/prod/upload"

def upload_file_to_aws(file_path: str) -> tuple[bool, str]:
    """
    Uploads the content of a JSON file to the AWS API endpoint.

    Args:
        file_path: The path to the JSON file to upload.

    Returns:
        A tuple containing:
        - bool: True if upload was successful, False otherwise.
        - str: A message indicating the result or error.
    """
    if not os.path.exists(file_path):
        return False, f"Error: File not found at {file_path}"

    # Load the file content (assumes it's valid JSON)
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return False, f"Error: Could not decode JSON from {file_path}"
    except Exception as e:
        return False, f"Error reading file {file_path}: {e}"

    headers = {"Content-Type": "application/json"}

    # Send the POST request to your API endpoint
    try:
        response = requests.post(API_ENDPOINT, json=data, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        return True, f"Successfully uploaded {os.path.basename(file_path)}. Status: {response.status_code}, Response: {response.text}"

    except requests.exceptions.RequestException as e:
        return False, f"Error sending request to {API_ENDPOINT}: {e}"
    except Exception as e:
        return False, f"An unexpected error occurred during upload: {e}"

def main():
    """Original command-line functionality."""
    if len(sys.argv) != 2:
        print("Usage: python upload_results.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    success, message = upload_file_to_aws(file_path)

    print(message)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
