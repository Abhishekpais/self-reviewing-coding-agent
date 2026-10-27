# Self-Healing Coding Agent: Dual-Agent Trajectory Evaluation & Deterministic Gating Framework

**Course & Project**: BAI586 (Mini Project, Semester V) — Department of Artificial Intelligence & Machine Learning, Government Engineering College Hassan  
**Project Guide**: Ms. Deeksha S  
**Project Team**:
* **Vaibhav Kumbar** (`4GH24AI055`) — Cloud GPU Infrastructure, Schema Design & LLM Client (`colab/`, `core/schemas.py`, `core/llm_client.py`)
* **Naunath** (`4GH24AI028`) — Target Coding Agent & Sandboxed ACI Tooling (`core/tools.py`, `core/coding_agent.py`)
* **Abhishek Pais** (`4GH24AI002`) — Trajectory Anti-Pattern Scanner & Process Reward Reviewer AI (`core/trajectory_analyzer.py`, `core/reviewer_agent.py`)
* **Vikas Malali** (`4GH24AI059`) — Deterministic Testing Gate, Sandbox Workspace Manager & Interactive CLI (`core/config.py`, `core/memory_manager.py`, `core/deterministic_gate.py`, `main.py`)

## Project Overview

Standard AI coding assistants only look at the final code output and often get stuck in repetitive loops, pick the wrong tool, skip verification tests, or break working code when trying to fix a bug (a problem known as **autonomous misevolution**).

The **Self-Healing Coding Agent** solves this at **$0 budget** using a **Dual-Agent Architecture** powered by open-weight [Gemma 4](https://ollama.com/library/gemma4) (`gemma4:12b` / `gemma4:e4b`) hosted on a free [Google Colab](https://colab.research.google.com/) T4 GPU via [Ollama](https://ollama.com/) and a keyless [Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/), while executing all code locally inside a strict **Python Virtual Environment (`.venv`)** and **In-Project Sandbox (`sandbox/workspaces/`)**:

1. **Level 1 Self-Healing (Target Coding Agent + Deterministic Gate)**: The **Target Coding Agent** solves programming tasks step-by-step using a **Thought-Action-Result (TAR)** loop (`PLAN` $\rightarrow$ `WRITE` $\rightarrow$ `EXECUTE` $\rightarrow$ `VERIFY` $\rightarrow$ `FINISH`) and logs every step as a JSON span. The **Reviewer AI** inspects the entire trajectory for **Tool Selection Errors**, **Workflow Execution Errors**, and **Code Generation Bugs**, then proposes a targeted repair prompt. When approved, the **Deterministic Gate** snapshots `src/`, applies the patch, runs syntax + AST + `.venv` runtime tests, and automatically rolls back if any test fails.
2. **Level 2 Self-Healing (Reviewer AI Meta-Feedback Learning)**: Through the **Human-in-the-Loop (HITL)** terminal interface, if the Reviewer AI itself makes a mistake or flags a false positive, the user can correct or reject the review. The system records a permanent `reviewer_self_healing_rule` in `feedback/reviewer_lessons.jsonl` and injects it into the Reviewer AI's system prompt on all future runs so the Reviewer AI learns from human corrections without expensive GPU fine-tuning.

## 1. How to Run the Project (Step-by-Step Setup Guide)

### Step 1.1: Clone the Repository & Activate the Local Virtual Environment (`.venv`)

Every command in this project must run inside a dedicated local Python virtual environment (`.venv`) so that both the CLI orchestrator and all sandboxed child processes remain isolated from your global operating system.

* **Using Git Bash (`MINGW64`) / Linux / macOS:**
```bash
git clone <YOUR_GITHUB_REPO_URL>
cd self_healing_agent

# Create and activate the local virtual environment
python -m venv .venv
source .venv/Scripts/activate   # On Linux/macOS use: source .venv/bin/activate

# Upgrade pip and install required packages
python -m pip install --upgrade pip
pip install -r requirements.txt

# Create your local .env configuration from the template
cp .env.example .env
```

* **Using Windows PowerShell:**
```powershell
git clone <YOUR_GITHUB_REPO_URL>
cd self_healing_agent

python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Step 1.2: Launch the Free Google Colab GPU Server (`Gemma 4` + Ollama + Cloudflared)

Because running a 12-billion-parameter LLM requires ~8 GB of GPU VRAM, the model runs on a free [Google Colab](https://colab.research.google.com/) Tesla T4 GPU (15 GB VRAM) while your local PC runs the lightweight CLI and sandboxed tools.

1. Open [Google Colab](https://colab.research.google.com/), create a new notebook, and select **Runtime $\rightarrow$ Change runtime type $\rightarrow$ T4 GPU**.
2. Paste and run **Cell 1** to install GPU detection utilities (`pciutils`, `zstd`), install [Ollama](https://ollama.com/), and pull `gemma4:12b` (or fallback `gemma4:e4b`):

3. Paste and run **Cell 2** to start a keyless [Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) and generate your public HTTPS URL:

4. Open your local `.env` file and paste the `COLAB_OLLAMA_URL` and `OLLAMA_MODEL` printed by Cell 2:

```ini
COLAB_OLLAMA_URL=https://your-generated-subdomain.trycloudflare.com
OLLAMA_MODEL=gemma4:12b
SANDBOX_ROOT=./sandbox/workspaces
ENFORCE_VENV=true
```

### Step 1.3: Verify Your Local `.venv`, Sandbox & Colab Connection

Run the Phase 1 verification script inside your activated `.venv` terminal:

```bash
python verify_phase1.py
```

Wait until you see `[PASS] Virtual Environment Active`, `[PASS] In-Project Sandbox Verified`, and `[PASS] Connected to Colab Ollama Tunnel`.

### Step 1.4: Run the Self-Healing Coding Agent CLI Commands

| CLI Command | What It Does |
| :--- | :--- |
| `python main.py status` | Displays your active `.venv` interpreter, sandbox root path, current `active_project_id`, `latest_trace_id`, and the count of **Learned Reviewer Rules**. |
| `python main.py code "<prompt>"` | Runs only the **Target Coding Agent** inside `sandbox/workspaces/<project_id>/src/`, executes the generated code using `.venv` Python, logs every Thought-Action-Result (TAR) span to `traces/trace_001.jsonl`, and prints a color-coded trajectory table. |
| `python main.py review` | Automatically locates the active project and latest trace via `sandbox/workspaces/active_session.json`, runs the **Deterministic Anti-Pattern Scanner** + **Reviewer AI**, prints the evaluation scorecard, and opens the **Human-in-the-Loop (HITL)** menu (`[A]`, `[E]`, `[R]`, `[S]`). |
| `python main.py heal "<prompt>"` | Runs the complete end-to-end closed loop in one command: **Code Generation $\rightarrow$ TAR Trace Logging $\rightarrow$ Reviewer AI Evaluation $\rightarrow$ Human-in-the-Loop Approval/Correction $\rightarrow$ Deterministic Gate Snapshot, Patch & Verification**. |

* **Example Closed-Loop Command:**
```bash
python main.py heal "Write a Python function merge_intervals(intervals) that merges overlapping [start, end] intervals, prints test results, and asserts edge cases."
```

## 2. Project Directory Layout

```text
self_healing_agent/
├── .env.example                       # Template environment variables for teammates
├── .gitignore                         # Ignores .venv, .env, and generated sandbox/workspaces/* data
├── requirements.txt                   # Python dependencies (pydantic, requests, python-dotenv, rich, typer, pytest)
├── verify_phase1.py                   # Phase 1 sanity check (.venv + sandbox confinement + Colab tunnel)
├── main.py                            # Interactive Rich & Typer CLI entry point + HITL loop
├── core/
│   ├── __init__.py                    # Marks core/ as a Python package
│   ├── config.py                      # Enforces .venv activation & locks paths inside sandbox/workspaces/
│   ├── schemas.py                     # Pydantic v2 data classes for Spans, Traces, Reviews & Feedback
│   ├── memory_manager.py              # Manages per-project folders, JSONL traces & active_session.json
│   ├── llm_client.py                  # REST client for Colab Ollama server with JSON schema enforcement
│   ├── tools.py                       # 5 sandboxed SWE-agent atomic tools + auto-filename generator
│   ├── coding_agent.py                # Target Coding Agent executing the TAR (Thought-Action-Result) loop
│   ├── trajectory_analyzer.py         # Rule-based scanner detecting structural workflow/tool anti-patterns
│   ├── reviewer_agent.py              # Open-Weight Reviewer AI (PRM) + meta-feedback rule injection
│   └── deterministic_gate.py          # Snapshot, syntax/AST/runtime test runner & automatic rollback gate
└── sandbox/
    └── workspaces/
        ├── .gitkeep                   # Keeps empty sandbox/workspaces/ directory tracked in Git
        ├── active_session.json        # Auto-generated pointer to active_project_id and latest_trace_id
        └── proj_<timestamp>_<slug>/   # Isolated per-project workspace created at runtime
            ├── metadata.json          # Project creation time and initial task prompt
            ├── src/                   # Agent-generated and self-healed Python files
            ├── tests/                 # Optional pytest regression tests
            ├── traces/                # Thought-Action-Result trajectory logs (trace_001.jsonl)
            ├── reviews/               # Structured Reviewer AI JSON reports (review_trace_001.json)
            └── feedback/              # Learned Reviewer self-correction rules (reviewer_lessons.jsonl)
```

## 3. Research Paper Mapping & File-by-File Technical Deep Dive (OOP Guide)

Every module in this project implements mechanisms from five peer-reviewed Software Engineering Agent research papers, written in clean, modular Object-Oriented Python (OOP). Below is a complete breakdown of **what each file does**, **which research paper inspired it**, and **how the Python classes, objects, and methods work under the hood** for any student who understands Python up to OOP (classes, objects, inheritance, methods, and exceptions).

| File Path | Primary Research Paper(s) Used | Core Mechanism Implemented |
| :--- | :--- | :--- |
| `core/config.py` | [OpenHands (Wang et al., 2024)](https://arxiv.org/abs/2407.16741) | Sandboxed runtime isolation, `.venv` interpreter locking (`VENV_PYTHON`), and path traversal protection (`ensure_inside_sandbox`). |
| `core/schemas.py` | [OpenHands (Wang et al., 2024)](https://arxiv.org/abs/2407.16741) & [Understanding SE Agents (Bouzenia & Pradel, 2025)](https://arxiv.org/abs/2506.18824) | Typed event-stream data models (`Observation`, `TraceSpan`, `MistakeItem`, `ReviewReport`, `ReviewerFeedbackItem`) inheriting from `pydantic.BaseModel`. |
| `core/memory_manager.py` | [OpenHands (Wang et al., 2024)](https://arxiv.org/abs/2407.16741) | `WorkspaceManager` class managing isolated per-project folders, `active_session.json` state tracking, and append-only `.jsonl` event logs. |
| `core/llm_client.py` | [SWE-agent (Yang et al., 2024)](https://arxiv.org/abs/2405.15793) | `OllamaColabClient` class enforcing structured JSON outputs via Pydantic JSON Schemas and auto-resolving remote Colab model tags. |
| `core/tools.py` | [SWE-agent (Yang et al., 2024)](https://arxiv.org/abs/2405.15793) & [AutoCodeRover (Zhang et al., 2024)](https://arxiv.org/abs/2404.05427) | `ToolRegistry` class implementing 5 linter-guarded Agent-Computer Interface (ACI) tools, 100-line output capping, and AST symbol inspection. |
| `core/coding_agent.py` | [RepairAgent (Bouzenia et al., 2024)](https://arxiv.org/abs/2403.17134) & [Understanding SE Agents (Bouzenia & Pradel, 2025)](https://arxiv.org/abs/2506.18824) | `CodingAgent` class driving the Finite State Machine (`PLAN` $\rightarrow$ `WRITE` $\rightarrow$ `EXECUTE` $\rightarrow$ `VERIFY` $\rightarrow$ `FINISH`) and TAR trajectory loop. |
| `core/trajectory_analyzer.py` | [Understanding SE Agents (Bouzenia & Pradel, 2025)](https://arxiv.org/abs/2506.18824) | `DeterministicTrajectoryScanner` class detecting recurring LLM failure motifs (action loops, thought-action mismatch, skipped verification). |
| `core/reviewer_agent.py` | [Understanding SE Agents (Bouzenia & Pradel, 2025)](https://arxiv.org/abs/2506.18824) & [RepairAgent (Bouzenia et al., 2024)](https://arxiv.org/abs/2403.17134) | `ReviewerAgent` class combining heuristic trajectory scans with an LLM Process Reward Model (PRM), confidence gating, and meta-feedback learning. |
| `core/deterministic_gate.py` | [AutoCodeRover (Zhang et al., 2024)](https://arxiv.org/abs/2404.05427) & [OpenHands (Wang et al., 2024)](https://arxiv.org/abs/2407.16741) | `DeterministicGate` class creating filesystem snapshots, running syntax/AST/runtime verification, and rolling back failed patches. |
| `main.py` | All 5 Papers (Integrated Orchestrator) | CLI controller connecting `CodingAgent`, `ReviewerAgent`, `DeterministicGate`, and the Human-in-the-Loop (HITL) meta-feedback workflow. |

### 3.1 `core/config.py` — Runtime Isolation & Sandbox Security Guard

* **What It Does**: Loads environment variables from `.env`, verifies that the user is running inside the `.venv` virtual environment, stores the exact file path to the `.venv` Python executable (`VENV_PYTHON = sys.executable`), and blocks any file operation from escaping `self_healing_agent/sandbox/workspaces/`.
* **Research Paper Connection**: Inspired by the sandboxed execution container architecture of [OpenHands (Wang et al., 2024, arXiv:2407.16741)](https://arxiv.org/abs/2407.16741), adapted for a low-spec local PC without requiring Docker overhead.
* **OOP & Python Technical Details**:
  * **Path Objects (`pathlib.Path`)**: Instead of error-prone string concatenation (`"sandbox/" + name`), it uses Python's object-oriented `Path` class (`PROJECT_ROOT = Path(__file__).resolve().parent.parent`).
  * **`verify_runtime_isolation()`**: Checks `sys.prefix != sys.base_prefix`. In Python, when a virtual environment is active, `sys.prefix` points to `.venv` while `sys.base_prefix` points to the global Python installation. If they are equal, `.venv` is not active and the function raises a `RuntimeError` immediately.
  * **`ensure_inside_sandbox(path: Path) -> Path`**: Calls `path.resolve()` (which expands any `../` relative jumps into a real absolute path) and calls `.is_relative_to(SANDBOX_ROOT)`. If an LLM ever tries to read or overwrite `../../Windows/system.ini` or `../.env`, Python raises a `PermissionError` before the file can be touched.

### 3.2 `core/schemas.py` — Object-Oriented Data Contracts (`Pydantic` Models)

* **What It Does**: Defines the blueprint classes for every piece of data that flows through the system: tool outputs (`Observation`), single agent steps (`TraceSpan`), detected errors (`MistakeItem`), full reviewer evaluations (`ReviewReport`), and user lessons (`ReviewerFeedbackItem`).
* **Research Paper Connection**: Combines the typed event-stream logging of [OpenHands (arXiv:2407.16741)](https://arxiv.org/abs/2407.16741) with the **Thought-Action-Result (TAR)** trajectory structure and error taxonomy of [Understanding SE Agents (Bouzenia & Pradel, 2025, arXiv:2506.18824)](https://arxiv.org/abs/2506.18824).
* **OOP & Python Technical Details**:
  * **Inheritance (`class TraceSpan(BaseModel)`)**: Every class in `core/schemas.py` inherits from `pydantic.BaseModel` ([Pydantic Documentation](https://www.google.com/search?q=https://docs.pydantic.dev/latest/)). In standard OOP, you write a lengthy `__init__(self, ...)` method and manually check types (`if not isinstance(step_index, int): raise TypeError`). By inheriting from `BaseModel`, Pydantic automatically generates `__init__`, validates data types at runtime, and provides built-in serialization methods:
    * `span.model_dump_json()`: Converts a Python object into a JSON string to save to disk.
    * `TraceSpan.model_validate_json(line)`: Reads a JSON string from disk or from the LLM and reconstructs a validated Python object.
  * **Object Composition**: Notice how `TraceSpan` contains an attribute `observation: Observation`, and `ReviewReport` contains `mistakes_found: list[MistakeItem]`. In OOP, building complex classes out of smaller specialized classes is called **composition**.
  * **Strict Enumerations (`Literal[...]`)**: Fields like `workflow_state: Literal["PLAN", "WRITE", "EXECUTE", "VERIFY", "FINISH"]` and `category: Literal["TOOL_SELECTION_ERROR", "WORKFLOW_EXECUTION_ERROR", "CODE_GENERATION_BUG"]` prevent invalid strings from ever entering your logs.

### 3.3 `core/memory_manager.py` — `WorkspaceManager` Class (Per-Project Storage & Session Pointer)

* **What It Does**: Creates and manages dedicated folders for every coding task inside `sandbox/workspaces/<project_id>/` (with subfolders `src/`, `tests/`, `traces/`, `reviews/`, and `feedback/`) and maintains `sandbox/workspaces/active_session.json` so the Reviewer AI always knows which project and trace are active.
* **Research Paper Connection**: Implements the persistent workspace state and event-log persistence pattern from [OpenHands (arXiv:2407.16741)](https://arxiv.org/abs/2407.16741).
* **OOP & Python Technical Details**:
  * **Encapsulation in `WorkspaceManager`**:
    * **`__init__(self, sandbox_root)`**: Stores `self.sandbox_root` and `self.session_file` (`active_session.json`) as instance attributes, validating both with `ensure_inside_sandbox()`.
    * **`@staticmethod def _slugify(text)`**: Uses the `@staticmethod` decorator because converting a prompt like `"Write a palindrome checker!"` into `"write_a_palindrome_checker"` does not need access to `self`.
    * **`create_or_load_project(self, name_or_prompt, project_id)`**: Creates a unique folder `proj_<YYYYMMDD_HHMMSS>_<slug>`, initializes its 5 subdirectories (`src`, `tests`, `traces`, `reviews`, `feedback`), writes `metadata.json`, and updates `active_session.json`.
    * **`append_span(self, span: TraceSpan)` & `load_trace(self, ...)`**: Uses the **JSON Lines (`.jsonl`)** format where each line in `trace_001.jsonl` is one complete JSON `TraceSpan` object. Opening the file in append mode (`"a"`) means every step is saved to disk immediately in real time—even if a program is interrupted mid-run, all previous spans remain intact.
    * **`append_reviewer_feedback()` & `load_reviewer_lessons()`**: Stores and retrieves `ReviewerFeedbackItem` objects from `feedback/reviewer_lessons.jsonl` across all sandbox projects so lessons learned in one project benefit future projects.

### 3.4 `core/llm_client.py` — `OllamaColabClient` Class (Remote GPU Bridge & Schema Enforcement)

* **What It Does**: Sends prompts from your local PC over HTTPS to the [Ollama](https://ollama.com/) server running on Google Colab, automatically matches the installed Gemma model tag (`gemma4:12b` or `gemma4:e4b`), and forces the LLM to reply in valid JSON matching any Pydantic class.
* **Research Paper Connection**: Supports the structured Agent-Computer Interface (ACI) communication pattern from [SWE-agent (Yang et al., 2024, arXiv:2405.15793)](https://arxiv.org/abs/2405.15793), preventing free-text parsing failures in 12B models.
* **OOP & Python Technical Details**:
  * **Instance State & Lazy Caching (`self._resolved_model`)**: In `__init__`, `self._resolved_model` starts as `None`. The first time `resolve_active_model(self)` runs, it calls `GET /api/tags` on the Colab server to see which models are installed. Once matched (e.g., `gemma4:12b`), it caches the result in `self._resolved_model` so subsequent steps don't waste network calls checking `/api/tags` again.
  * **Generic Type Hinting (`response_model: Type[T] -> T`)**: The method `chat_structured(self, system_prompt, user_prompt, response_model, ...)` accepts *any* Pydantic class (such as `AgentStepResponse` from the Coding Agent or `LLMReviewAssessment` from the Reviewer Agent). It calls `response_model.model_json_schema()` and passes that schema into Ollama's `"format"` parameter. Ollama's token sampler then mathematically blocks the LLM from generating any token that violates that JSON schema!
  * **Fault Tolerance (Exponential Backoff)**: Wraps the `requests.post()` network call inside a `for attempt in range(1, max_retries + 1): try ... except` block, sleeping `2 ** attempt` seconds (`2s`, `4s`) if the Cloudflare tunnel has a momentary hiccup.

### 3.5 `core/tools.py` — `ToolRegistry` Class (Sandboxed ACI Tools & AST Inspector)

* **What It Does**: Provides the 5 atomic tools that the Target Coding Agent can call (`write_code_file`, `patch_code_file`, `read_code_file`, `inspect_ast_symbols`, `run_terminal_test`), automatically generates a clean Python filename if the user didn't provide one, validates syntax on every file edit, and runs scripts using `.venv` Python.
* **Research Paper Connection**:
  * **Linter-Guarded Atomic Editing & 100-Line Output Capping** come directly from [SWE-agent (Yang et al., 2024, arXiv:2405.15793)](https://arxiv.org/abs/2405.15793), which proved that coding agents perform dramatically better when syntax errors are rejected immediately at write-time and terminal outputs are truncated to 100 lines.
  * **AST Symbol Inspection (`inspect_ast_symbols`)** comes from [AutoCodeRover (Zhang et al., 2024, arXiv:2404.05427)](https://arxiv.org/abs/2404.05427), which parses code structure into Abstract Syntax Trees (classes, functions, line numbers) instead of dumping raw text.
* **OOP & Python Technical Details**:
  * **Dispatcher Pattern (`execute_tool(self, tool_name, arguments) -> Observation`)**: Acts as a single entry gateway. It records the start time using `time.perf_counter_ns()`, routes `tool_name` to the matching method (`self.write_code_file`, `self.patch_code_file`, etc.), catches any unexpected exceptions so the agent loop never crashes, calculates `duration_ms`, and always returns a standardized `Observation` object.
  * **Immediate Syntax Guard (`py_compile.compile`)**: Inside `write_code_file` and `patch_code_file`, right after writing the file, it runs Python's built-in bytecode compiler (`py_compile.compile(str(target), doraise=True)`). In `patch_code_file`, if the patch introduces a `SyntaxError`, it immediately restores `original` text and returns an `ERROR` observation telling the LLM what line had invalid syntax!
  * **Abstract Syntax Tree Parsing (`ast.parse` & `ast.walk`)**: In `inspect_ast_symbols`, Python's built-in `ast` module parses the source code into a tree of objects (`ast.ClassDef`, `ast.FunctionDef`), extracting function names, parameter names, and start/end line numbers (`node.lineno` to `node.end_lineno`).
  * **Isolated Subprocess Execution (`subprocess.run`)**: In `run_terminal_test`, it runs `[VENV_PYTHON, str(target_script)]` with `cwd=str(self.src_dir)` and `timeout=10`. If the generated code has an infinite `while True:` loop, `subprocess.TimeoutExpired` catches it after 10 seconds and returns `exit_code=124` without freezing your PC.

### 3.6 `core/coding_agent.py` — `CodingAgent` Class (FSM & TAR Execution Loop)

* **What It Does**: Takes a user's coding task (or a repair instruction from the Reviewer AI), runs up to `max_steps` iterations of **Thought $\rightarrow$ Action $\rightarrow$ Result**, executes tools via `ToolRegistry`, and logs every step as a `TraceSpan` in `traces/trace_<id>.jsonl`.
* **Research Paper Connection**: Implements the **Finite State Machine (FSM)** workflow progression (`PLAN` $\rightarrow$ `WRITE` $\rightarrow$ `EXECUTE` $\rightarrow$ `VERIFY` $\rightarrow$ `FINISH`) from [RepairAgent (Bouzenia et al., 2024, arXiv:2403.17134)](https://arxiv.org/abs/2403.17134) and records the **Thought-Action-Result (TAR)** trajectory defined in [Understanding SE Agents (Bouzenia & Pradel, 2025, arXiv:2506.18824)](https://arxiv.org/abs/2506.18824).
* **OOP & Python Technical Details**:
  * **Dependency Injection in `__init__`**: `CodingAgent.__init__(self, workspace_manager=None, llm_client=None)` accepts existing `WorkspaceManager` and `OllamaColabClient` objects (or creates default ones if `None`). In OOP, passing collaborator objects into `__init__` is called **dependency injection** and makes classes clean and reusable.
  * **Explicit Schema Classes (`ToolArgumentsSchema` & `AgentStepResponse`)**: Defines the exact JSON structure the LLM must return at every step (`workflow_state`, `thought`, `tool_selected`, `tool_arguments`, `final_summary`).
  * **Stateful History Accumulation (`run_coding_task`)**: Inside the `for step_idx in range(1, max_steps + 1):` loop, each step's `TraceSpan` is appended to `trace_<id>.jsonl` via `self.wm.append_span(span)` and summarized into `history_lines` so the LLM sees the exact `STDOUT` and `STDERR` of its previous actions on the next turn. When `workflow_state == "FINISH"`, the loop exits cleanly.

### 3.7 `core/trajectory_analyzer.py` — `DeterministicTrajectoryScanner` Class (Heuristic PRM Pre-Scanner)

* **What It Does**: Inspects a list of `TraceSpan` objects using fast, deterministic Python rules to catch structural workflow and tool mistakes *before* querying the Reviewer LLM.
* **Research Paper Connection**: Directly codifies the empirical failure taxonomy discovered across 120 agent trajectories in [Understanding Software Engineering Agents (Bouzenia & Pradel, 2025, arXiv:2506.18824)](https://arxiv.org/abs/2506.18824).
* **OOP & Python Technical Details**:
  * **Stateless Utility Method (`@staticmethod def scan(spans: list[TraceSpan]) -> list[MistakeItem]`)**: Iterates through the list of `TraceSpan` objects and checks 5 concrete conditions:
    1. **`STATE_TOOL_MISMATCH`**: Checks if `span.tool_selected in ("write_code_file", "patch_code_file")` while `span.workflow_state == "PLAN"` instead of `"WRITE"`.
    2. **`THOUGHT_ACTION_MISMATCH`**: Checks if `span.thought` states an intention to execute/run the script, but `span.tool_selected == "read_code_file"`.
    3. **`REPEATED_FAILING_TOOL`**: Compares `spans[idx]` with `spans[idx - 1]` to detect when the agent calls the exact same tool with identical arguments immediately after an `ERROR` observation (an action loop).
    4. **`SKIPPED_EXECUTION_VERIFICATION`**: Tracks `last_write_step` and `last_successful_test_step`. If `last_write_step > last_successful_test_step`, the agent edited code and finished without verifying that it runs!
    5. **`UNRESOLVED_RUNTIME_ERROR`**: Checks if the final `run_terminal_test` span ended with `status == "ERROR"`.

### 3.8 `core/reviewer_agent.py` — `ReviewerAgent` Class (LLM-as-a-Judge & Self-Improving Memory)

* **What It Does**: Automatically loads the latest trace and generated code from the active sandbox project, loads all past user corrections (`reviewer_lessons.jsonl`), runs `DeterministicTrajectoryScanner`, queries `Gemma 4` (`temperature=0.0`) as a **Process Reward Model (PRM)**, applies a confidence gate (`confidence_score >= 0.75`), and saves the resulting `ReviewReport` to `reviews/review_<trace_id>.json`.
* **Research Paper Connection**: Combines the trajectory evaluation rubric from [Understanding SE Agents (arXiv:2506.18824)](https://arxiv.org/abs/2506.18824) with confidence gating from [RepairAgent (arXiv:2403.17134)](https://arxiv.org/abs/2403.17134), extended with **In-Context Meta-Feedback Learning** so the Reviewer AI heals its own evaluation bias.
* **OOP & Python Technical Details**:
  * **Dynamic Prompt Injection (`_build_self_healing_rules_block`)**: Reads `ReviewerFeedbackItem` objects from `self.wm.load_reviewer_lessons()` and formats them into a `CRITICAL SELF-CORRECTION RULES FROM USER FEEDBACK` block injected directly into `REVIEWER_SYSTEM_PROMPT`.
  * **Set-Based Deduplication (`seen_keys`)**: When merging mistakes found by `DeterministicTrajectoryScanner` with `llm_eval.llm_detected_mistakes`, it stores `(m.span_id, m.anti_pattern_code)` tuples inside a Python `set` (`seen_keys`). Because set lookups are $O(1)$, duplicate findings are filtered out cleanly before constructing the final `ReviewReport` object.

### 3.9 `core/deterministic_gate.py` — `DeterministicGate` Class (Anti-Misevolution Safety Layer)

* **What It Does**: Protects the codebase when applying a self-healing patch. It backs up `src/` to `.snapshot_src/`, runs 3 deterministic checks (AST/Syntax compilation, `.venv` subprocess execution with `exit_code == 0`, and optional `pytest` suite), commits the code if all pass, or restores `.snapshot_src/` if any check fails.
* **Research Paper Connection**: Implements the patch regression validation gate from [AutoCodeRover (Zhang et al., 2024, arXiv:2404.05427)](https://arxiv.org/abs/2404.05427) and [OpenHands (arXiv:2407.16741)](https://arxiv.org/abs/2407.16741) to prevent **autonomous misevolution** (where an unverified AI fix degrades working software).
* **OOP & Python Technical Details**:
  * **Python `@dataclass` (`class GateResult`)**: Uses `@dataclass` from Python's standard `dataclasses` module to create a lightweight result object holding `passed: bool`, `rolled_back: bool`, `summary: str`, and `details: list[str]`.
  * **Atomic Filesystem Snapshot & Rollback (`shutil.copytree` & `shutil.rmtree`)**:
    * `create_snapshot(project_id)` copies the entire `src/` folder into `.snapshot_src/` before the Coding Agent touches any file.
    * Inside `verify_and_gate(project_id)`, if `py_compile`, `ast.parse`, or `subprocess.run([VENV_PYTHON, ...])` fails on any `.py` file, it immediately calls `self.restore_snapshot(project_id)` to restore the clean backup and returns `GateResult(passed=False, rolled_back=True, ...)`.

### 3.10 `main.py` & `verify_phase1.py` — CLI Controller, HITL Loop & Setup Verifier

* **What They Do**:
  * `verify_phase1.py` is a diagnostic script that tests `.venv` isolation, sandbox confinement, and the Colab HTTPS tunnel before running the agent.
  * `main.py` uses [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/) to provide the terminal interface (`code`, `review`, `heal`, `status`) and the interactive **Human-in-the-Loop (HITL)** prompt (`_interactive_hitl_loop`).
* **OOP & Python Technical Details**:
  * **Decorator-Based CLI Routing (`@app.command()`)**: Creating `app = typer.Typer()` and decorating functions (`@app.command() def heal(...)`) automatically turns Python function arguments and type annotations (`prompt: str`, `max_steps: int = 6`) into documented command-line flags (`--project`, `--file`, `--max-steps`).
  * **Closed-Loop Orchestration (`_interactive_hitl_loop` & `_execute_gated_self_healing`)**: Connects all 4 core classes (`WorkspaceManager`, `CodingAgent`, `ReviewerAgent`, and `DeterministicGate`) into a clean interactive loop where the user controls whether to approve a fix (`[A]`), teach the Reviewer AI a new rule (`[E]`), or log a false positive (`[R]`).

## 4. Academic Citations & References

1. **OpenHands (Sandboxed Event-Stream Architecture)**  
   Xingyao Wang, Boxuan Li, Yufan Song, Frank F. Xu, Xiangru Tang, Mingchen Zhuge, Jiayi Pan, Yueqi Song, Bowen Li, Jaskirat Singh, Hoang H. Tran, Fuqiang Li, Ren Ma, Mingzhang Zheng, Bill Qian, Yanjun Shao, Niklas Muennighoff, Yizhe Zhang, Binyuan Hui, Junyang Lin, Robert Brennan, Hao Peng, Heng Ji, and Graham Neubig. 2024. *OpenHands: An Open Platform for AI Software Developers as Generalist Agents*. arXiv preprint [arXiv:2407.16741](https://arxiv.org/abs/2407.16741).

2. **RepairAgent (Autonomous FSM & Confidence-Gated Program Repair)**  
   Islem Bouzenia, Premkumar Devanbu, and Michael Pradel. 2024. *RepairAgent: An Autonomous, LLM-Based Agent for Program Repair*. arXiv preprint [arXiv:2403.17134](https://arxiv.org/abs/2403.17134).

3. **Understanding Software Engineering Agents (TAR Trajectory Evaluation & Failure Taxonomy)**  
   Islem Bouzenia and Michael Pradel. 2025. *Understanding Software Engineering Agents: A Study of Thought-Action-Result Trajectories*. arXiv preprint [arXiv:2506.18824](https://arxiv.org/abs/2506.18824).

4. **AutoCodeRover (AST Context Retrieval & Automated Patch Validation)**  
   Yuntong Zhang, Haifeng Ruan, Zhiyu Fan, and Abhik Roychoudhury. 2024. *AutoCodeRover: Autonomous Program Improvement*. In Proceedings of the 33rd ACM SIGSOFT International Symposium on Software Testing and Analysis (ISSTA 2024), [arXiv:2404.05427](https://arxiv.org/abs/2404.05427).

5. **SWE-agent (Agent-Computer Interface Design & Linter-Guarded Atomic Tools)**  
   John Yang, Carlos E. Jimenez, Alexander Wettig, Kilian Lieret, Shunyu Yao, Karthik Narasimhan, and Ofir Press. 2024. *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering*. In Advances in Neural Information Processing Systems (NeurIPS 2024), [arXiv:2405.15793](https://arxiv.org/abs/2405.15793).

6. **Core Open-Source Frameworks & Runtime Documentation**  
   * Google DeepMind. 2026. *Gemma 4 Open-Weight Model Family on Ollama*. [https://ollama.com/library/gemma4](https://ollama.com/library/gemma4) and [https://ai.google.dev/gemma/docs/integrations/ollama](https://ai.google.dev/gemma/docs/integrations/ollama).  
   * Pydantic Team. 2026. *Pydantic v2 Data Validation and JSON Schema Enforcement*. [https://docs.pydantic.dev/latest/](https://www.google.com/search?q=https://docs.pydantic.dev/latest/).  
   * Cloudflare. 2026. *TryCloudflare Keyless Quick Tunnels (`cloudflared`)*. [https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/).
