# Primary Directive
- Think in English, interact with the user in Japanese.

# Copilot Instructions

## Communication
- Respond in Japanese.
- Before implementing anything, confirm the intended work with the user and obtain approval.
- Ask the user for clarification when necessary.
- After completing work, explain what was done and describe the next actions the user can take.

## Workflow
- If the task involves many steps, divide the work into stages and make git commits along the way.
  - Use semantic commits.

## Development Environment & Tools

### Package Management
- Always use `uv` to run commands.
  - Normally use `uv run` instead of `uv run python`.
- When adding libraries, install them via `uv`.
- Libraries used only during development must be installed as dev dependencies.

### Code Formatting
- After outputting code, format it using `ruff`.
- If ruff is not installed, prompt the user to install it with commands: `uv add --dev ruff`
- Also execute `check --fix --select I` on the target file to organize import statements.

### Other
- If command output is not visible, check with `get last command` or `check background terminal`.

## Project Structure
- Place source code under the `src` directory.
- Place test code under the `tests` directory.
- Place documentation under the `docs` directory.
- Store processed data in the `data` directory, in subdirectories per experimental condition.
- Store processing results in the `results` directory, in subdirectories per experimental condition.
- Temporary throwaway scripts should be placed in a `tmp` directory and added to `.gitignore`.

## Code Style

### General Policy
- Do not use emojis in code.
- Collect all import statements at the top of each file.
- Add type hints wherever possible.
- Avoid writing scripts that rely on command-line execution arguments unless necessary.

### Python-Specific
- Python 3.10+ is used, so use modern type-hint syntax.
  - Do not import `List` or `Dict` from typing; use built-in `list`, `dict`, etc.

### File Operations
- Always specify files using relative paths.
- Use `pathlib` for file operations.

## Libraries & Dependencies
- Use `polars` instead of pandas for data analysis.
- Use `matplotlib` for visualization.

## Data Processing
- When processing many datasets, organize them in separate directories per dataset.
- When using loops, display processing progress.

## Visualization

### Basic Settings
- Use `matplotlib` for visualization.
- Always add graph title, axis labels, and legends.

### Style
- Do not use Japanese in titles or other elements.
- Use fonts **TeX Gyre Termes** or **Times New Roman**.
  - TeX Gyre Termes is stored in the `asset/fonts` directory.
- Use `rcParams` to specify font size; do not override them unless necessary.

### Layout
- Use `tight_layout()` for automatic layout adjustment.
- When drawing many figures repeatedly, free memory using `fig.close()`.

## Documentation
- Documentation must be created in Markdown format.
- Always include a table of contents.
- Store documentation in the `docs` directory.