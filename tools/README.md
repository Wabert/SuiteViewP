# Tools

This directory contains small, single-purpose helper scripts used by AI
assistants (and developers) to perform tasks that require code execution.

## Rules

- **No inline execution.** All Python execution must go through scripts in
  this directory — never via `python -c "..."` or similar inline commands.
- **Single-purpose.** Each script should do one thing well.
- **Auditable.** Keep scripts small and easy to review.
- **CLI input/output.** Accept input via command-line args (prefer JSON as a
  single argument) and write output to stdout as JSON.
- **Reuse.** Check for existing scripts before creating new ones.

## Usage

```powershell
python tools/<script>.py '<json_args>'
```
