# AICommit

AICommit is a command-line tool that uses OpenAI’s GPT models to generate meaningful git commit messages based on the changes in your repository. It analyzes your git diffs and creates concise, conventional commit messages to streamline your workflow.

## Features

- **Automated Commit Messages:** Generate commit messages without typing them manually.
- **Conventional Commits Compliance:** Follows the Conventional Commitshttps://www.conventionalcommits.org/ specification for clear and consistent commit history.
- **Easy Integration:** Simple to install and use with your existing git workflow.

-–

## Installation

### Local Installation from Source

To install AICommit locally from the source code, ensure you have Python 3.6 or later installed.

	1.	**Clone the Repository**
```bash
git clone https://github.com/yourusername/aicommit.git
```
	2.	**Navigate to the Project Directory**
```bash
cd aicommit
```
	3.	**Install the Package Locally**
Install the package using `pip`:
```bash
pip install .
```
Or, for development purposes, install it in editable mode:
```bash
pip install -e .
```
This will install the `aicommit` command-line tool on your system.

### Global Installation via PyPI (Once Published)

After AICommit is published to PyPI, you can install it globally using `pip`:

```bash
pip install aicommit
```

This will make the `aicommit` command available globally on your system.

-–

## Usage

### Setting Up OpenAI API Key

Before using AICommit, you need to set your OpenAI API key as an environment variable:

```bash
export OPENAI_API_KEY=‘your-api-key-here’
```

Replace `‘your-api-key-here’` with your actual OpenAI API key.

### Generating Commit Messages

In your git repository, after making changes, simply run:

```bash
aicommit
```

AICommit will:

- Detect files with changes.
- Generate commit messages for each file using OpenAI’s GPT models.
- Stage and commit the changes with the generated messages.

### Example

```bash
$ aicommit
Committed example.py with message: feat: add data processing function
```

-–

## Configuration

You can customize AICommit’s behavior by modifying the source code or adding command-line arguments as needed.

-–

## Development

### Requirements

- Python 3.6 or higher
- Git
- OpenAI Python library (`openai`)

### Installing Dependencies

Install the required Python packages:

```bash
pip install .
```

-–

## Contributing

Contributions are welcome! Please follow these steps:

	1.	**Fork the Repository**
Click the “Fork” button at the top of the repository page to create a copy in your GitHub account.
	2.	**Clone Your Fork**
```bash
git clone https://github.com/web-mech/aicommit.git
```
	3.	**Create a New Branch**
```bash
git checkout -b feature/your-feature-name
```
	4.	**Make Changes and Commit**
```bash
git commit -am ‘Add new feature’
```
	5.	**Push to Your Fork**
```bash
git push origin feature/your-feature-name
```
	6.	**Submit a Pull Request**
Open a pull request on the original repository with a clear description of your changes.

-–

## License

This project is licensed under the MIT License - see the LICENSELICENSE file for details.

-–

## Contact

For questions or support, please open an issue on the GitHub repository