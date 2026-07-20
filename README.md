# benzaiten

`benzaiten` is a local multi-model AI infrastructure project for processing documents, extracting structured knowledge, coordinating local language models, and building a research vault.

## Project goals

* Process PDF and other research documents
* Convert source files into clean Markdown
* Split documents into reliable model-ready chunks
* Use different local models for different roles
* Preserve artifacts, provenance, retries, and task state
* Produce structured notes for a local knowledge vault

## Model roles

* **Qwen** — fast utility model, document preparation, coding assistance, and routine tasks
* **Gemma** — deeper reasoning, summarization, critique, and verification

The models are independent workers coordinated by transparent Python code.

## Architecture

`benzaiten` is designed as a local artifact and state-machine system.

* **SQLite** stores task state, locks, retries, and provenance
* **workspace/** stores raw and intermediate artifacts
* **vault/** stores final structured knowledge
* **vLLM or compatible endpoints** provide model serving
* **software parsers** perform document extraction
* **Python** validates and executes model-proposed actions

Models may propose actions, but they do not directly control files, scripts, or system state.

## Current status

Early development.

Current work includes:

* core configuration and topology structures
* PDF preparation pipeline
* OpenAI-compatible model client
* model response and error handling

## Planned first workflow

```text
PDF
→ extraction
→ cleaned Markdown
→ chunking
→ model analysis
→ structured research note
→ knowledge vault
```

## Development principles

* Local and transparent
* Small, understandable modules
* Deterministic Python control
* Models are workers, not trusted orchestrators
* No premature generalization
* Working baseline before optimization
* Preserve intermediate artifacts for debugging

## Status notice

The project is experimental and not yet ready for production use.

