import subprocess
import openai
import os

# Set your OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_diffed_files():
    """Get the list of files with changes."""
    result = subprocess.run(['git', 'diff', '--name-only'], capture_output=True, text=True)
    return result.stdout.strip().split('\n')

def get_file_diff(file_path):
    """Get the diff of a specific file."""
    result = subprocess.run(['git', 'diff', file_path], capture_output=True, text=True)
    return result.stdout

def generate_commit_message(diff):
    """Generate a commit message using OpenAI API."""
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=f"Generate a Conventional Commit message for the following changes. "
               f"Use 'fix' for patches, 'feat' for minor features, and 'BREAKING CHANGE' for breaking changes:\n\n{diff}",
        max_tokens=60
    )
    return response.choices[0].text.strip()

def commit_changes(files):
    """Commit changes with generated commit messages."""
    for file in files:
        diff = get_file_diff(file)
        if diff:
            commit_message = generate_commit_message(diff)
            subprocess.run(['git', 'add', file])
            subprocess.run(['git', 'commit', '-m', commit_message])
            print(f"Committed {file} with message: {commit_message}")

def main():
    files = get_diffed_files()
    if files:
        commit_changes(files)
    else:
        print("No changes to commit.")

if __name__ == "__main__":
    main()