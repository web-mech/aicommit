import subprocess
import os
from openai import OpenAI

# Initialize the OpenAI client
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

def get_diffed_files():
    """Get the list of files with changes."""
    result = subprocess.run(['git', 'diff', '--name-only'], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error getting diffed files:", result.stderr)
        return []
    return result.stdout.strip().split('\n')

def get_file_diff(file_path):
    """Get the diff of a specific file."""
    result = subprocess.run(['git', 'diff', file_path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error getting diff for {file_path}:", result.stderr)
        return ""
    return result.stdout

def generate_commit_message(diff):
    """Generate a commit message using OpenAI API."""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant for generating commit messages."},
                {"role": "user", "content": f"Generate a Conventional Commit message for the following changes. "
                                             f"Use 'fix' for patches, 'feat' for minor features, and 'BREAKING CHANGE' for breaking changes:\n\n{diff}"}
            ],
            max_tokens=120
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error generating commit message: {e}")
        return "chore: update"

def commit_changes(files):
    """Commit changes with generated commit messages."""
    for file in files:
        diff = get_file_diff(file)
        if diff:
            commit_message = generate_commit_message(diff)
            try:
                subprocess.run(['git', 'add', file], check=True)
                subprocess.run(['git', 'commit', '-m', commit_message], check=True)
                print(f"Committed {file} with message: {commit_message}")
            except subprocess.CalledProcessError as e:
                print(f"Error committing {file}: {e}")

def main():
    files = get_diffed_files()
    if files:
        commit_changes(files)
    else:
        print("No changes to commit.")

if __name__ == "__main__":
    main()