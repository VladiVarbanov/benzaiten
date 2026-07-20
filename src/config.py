"""Concrete benzaiten configuration.

This file contains the actual hosts, compute nodes, models, agents,
paths, and registries for Vladimir's local benzaiten setup.
"""

from pathlib import Path

from structures import (
    AgentStruct,
    HostStruct,
    ModelStruct,
    make_compute_node,
    make_memory,
)


# =====================================================================
# 1. LOCAL ORCHESTRATOR IDENTITY
# =====================================================================

NODE_ID = "pc1"
NODE_ROLE = "orchestrator"
ORCHESTRATOR_ROOT = Path("/home/vladi/local_ai/benzaiten")
PROJECT_ROOT = ORCHESTRATOR_ROOT  # Backward-compatible alias for now.


# =====================================================================
# 2. SQLITE EXECUTION LEDGER
# =====================================================================

DB_PATH = ORCHESTRATOR_ROOT / "benzaiten.db"
DB_WAL_MODE = True
DB_BUSY_TIMEOUT_MS = 15_000

# Important: only the orchestrator host owns SQLite writes.
DATABASE_OWNER_PHYS_HOST = "pc1"
ALLOW_REMOTE_DB_WRITES = False


# =====================================================================
# 3. DIRECTORY LAYOUT
# =====================================================================

SRC_DIR = ORCHESTRATOR_ROOT / "src"
PROMPTS_DIR = ORCHESTRATOR_ROOT / "prompts"

WORKSPACE_DIR = ORCHESTRATOR_ROOT / "workspace"
INBOX_DIR = WORKSPACE_DIR / "inbox"
ARTIFACTS_DIR = WORKSPACE_DIR / "artifacts"
TMP_DIR = WORKSPACE_DIR / "tmp"

VAULT_DIR = ORCHESTRATOR_ROOT / "vault"
OKF_DIR = VAULT_DIR / "OKF"
SOURCES_DIR = VAULT_DIR / "sources"
OKF_PROJECTS_DIR = VAULT_DIR / "projects"
OKF_CONCEPTS_DIR = VAULT_DIR / "concepts"
# Later, maybe:
# OKF_CLAIMS_DIR = VAULT_DIR / "claims"


# =====================================================================
# 4. DIRECTORY SANDBOXING
# =====================================================================

SANDBOX_PATHS = [
    WORKSPACE_DIR,
    VAULT_DIR,
]

FILE_USE_ATOMIC_REPLACE = True
FILE_TEMP_SUFFIX = ".tmp"

ALLOW_SHELL = False
ALLOW_DELETE = False
REQUIRE_ARTIFACT_HASHES = True
IMMUTABLE_ARTIFACTS = True


# =====================================================================
# 5. PHYSICAL HOST INSTANCES
# =====================================================================

PC1_HOST = HostStruct(
    phys_host="pc1",
    system_hostname="Vladi-at-work-PC",
    address_local="192.168.50.1",
    address_external=None,
    access_type="local",
    shared_root=ORCHESTRATOR_ROOT,
    ssh_port=None,
    ssh_user=None,
    ssh_key_env=None,
)

PC2_HOST = HostStruct(
    phys_host="pc2",
    system_hostname="Vladi-at-work-2",
    address_local="192.168.50.2",
    address_external=None,
    access_type="ssh",
    shared_root=Path("/home/vladi/local_ai/benzaiten"),
    ssh_port=22,
    ssh_user="vladi",
    ssh_key_env="BENZAITEN_PC2_SSH_KEY",
)


# =====================================================================
# 6. MEMORY PRIMITIVES
# =====================================================================

PC1_CPU_MEMORY = make_memory(
    total_gb=32.0,
    reserved_system_gb=8.0,
    memory_type="system_ram",
)

PC1_GPU0_MEMORY = make_memory(
    total_gb=16.0,
    reserved_system_gb=0.7,
    memory_type="vram",
)

PC2_CPU_MEMORY = make_memory(
    total_gb=32.0,
    reserved_system_gb=4.0,
    memory_type="system_ram",
)

PC2_GPU0_MEMORY = make_memory(
    total_gb=16.0,
    reserved_system_gb=0.7,
    memory_type="vram",
)

# Ordered but not necessarily installed yet. Keep commented until physically present.
# PC1_GPU1_MEMORY = make_memory(
#     total_gb=32.0,
#     reserved_system_gb=0.7,
#     memory_type="vram",
# )


# =====================================================================
# 7. COMPUTE NODE INSTANCES
# =====================================================================

PC1_CPU = make_compute_node(
    phys_host="pc1",
    device_type="cpu",
    device_id=None,
    device_name="System_CPU",
    memory=PC1_CPU_MEMORY,
)

PC1_GPU0 = make_compute_node(
    phys_host="pc1",
    device_type="gpu",
    device_id=0,
    device_name="RTX_5070_Ti_16GB",
    memory=PC1_GPU0_MEMORY,
)

PC2_CPU = make_compute_node(
    phys_host="pc2",
    device_type="cpu",
    device_id=None,
    device_name="System_CPU",
    memory=PC2_CPU_MEMORY,
)

PC2_GPU0 = make_compute_node(
    phys_host="pc2",
    device_type="gpu",
    device_id=0,
    device_name="RTX_5070_Ti_16GB",
    memory=PC2_GPU0_MEMORY,
)

# Future RTX PRO 4500 32GB placement example, after installation:
# PC1_GPU1 = make_compute_node(
#     phys_host="pc1",
#     device_type="gpu",
#     device_id=1,
#     device_name="RTX_PRO_4500_32GB",
#     memory=PC1_GPU1_MEMORY,
# )


# =====================================================================
# 8. MODEL INSTANCES
# =====================================================================

QWEN_MODEL = ModelStruct(
    model_name="qwen3-30b-a3b-nvfp4",
    node=PC1_GPU0.node,
    interface_type="openai_compatible_api",
    endpoint_url="http://127.0.0.1:8001/v1",
    endpoint_port=8001,
    api_key_env="BENZAITEN_QWEN_API_KEY",
    cli_command=None,
    working_dir=None,
    role=["agent", "coder", "summarizer"],
    context_tokens=8192,
    output_tokens=800,
    temperature=0.1,
)

DIFFUSION_GEMMA_MODEL = ModelStruct(
    model_name="diffusiongemma-26b-a4b-it-gguf",
    node=PC2_GPU0.node,
    interface_type="cli",
    endpoint_url=None,
    endpoint_port=None,
    api_key_env=None,
    cli_command=(
        "CUDA_VISIBLE_DEVICES=0 "
        "/home/vladi/local_ai/llama.cpp-diffusiongemma/build/bin/llama-cli "
        "-m /home/vladi/local_ai/models/diffusiongemma-26B-A4B-it-Q4_K_M.gguf "
        "--prompt-file {prompt_path}"
    ),
    working_dir=Path("/home/vladi/local_ai"),
    role=["reasoning", "reviewer"],
    context_tokens=4096,
    output_tokens=3000,
    temperature=0.2,
)


# =====================================================================
# 9. AGENT INSTANCES
# =====================================================================

BENZAITEN_ORCHESTRATOR = AgentStruct(
    name="benzaiten_orchestrator",
    node=PC1_CPU.node,
    interface_type="python_subprocess",
    role=["orchestrator", "state_machine"],
    uses_model=None,
    max_tool_calls_per_task=20,
    max_file_read_lines=400,
    session_isolation=True,
)

QWEN_AGENT = AgentStruct(
    name="qwen_anythingllm_agent",
    node=PC1_CPU.node,
    interface_type="anythingllm_api",
    role=["agent", "operator"],
    uses_model="qwen",
    max_tool_calls_per_task=20,
    max_file_read_lines=400,
    session_isolation=True,
)

GEMMA_REVIEWER_AGENT = AgentStruct(
    name="gemma_reviewer_agent",
    node=PC2_CPU.node,
    interface_type="python_subprocess",
    role=["reviewer", "reasoning_worker"],
    uses_model="diffusion_gemma",
    max_tool_calls_per_task=8,
    max_file_read_lines=400,
    session_isolation=True,
)


# =====================================================================
# 10. REGISTRIES
# =====================================================================

HOSTS = {
    PC1_HOST.phys_host: PC1_HOST,
    PC2_HOST.phys_host: PC2_HOST,
}

COMPUTE_NODES = {
    PC1_CPU.node: PC1_CPU,
    PC1_GPU0.node: PC1_GPU0,
    PC2_CPU.node: PC2_CPU,
    PC2_GPU0.node: PC2_GPU0,
    # PC1_GPU1.node: PC1_GPU1,  # enable after RTX PRO 4500 is installed
}

MODELS = {
    "qwen": QWEN_MODEL,
    "diffusion_gemma": DIFFUSION_GEMMA_MODEL,
}

AGENTS = {
    "benzaiten_orchestrator": BENZAITEN_ORCHESTRATOR,
    "qwen_agent": QWEN_AGENT,
    "gemma_reviewer_agent": GEMMA_REVIEWER_AGENT,
}


# =====================================================================
# 11. ACTION REGISTRY AND DETERMINISTIC STATE MACHINE
# =====================================================================

ACTIONS = {
    "ingest_file": {
        "enabled": True,
        "input_kinds": ["source_file"],
        "output_kind": "ingested_file",
    },
    "convert_to_md": {
        "enabled": True,
        "input_kinds": ["ingested_file"],
        "output_kind": "markdown",
    },
    "summarize": {
        "enabled": True,
        "model": "qwen",
        "prompt": "summarize.md",
        "input_kinds": ["markdown"],
        "output_kind": "summary",
    },
    "extract_okf": {
        "enabled": True,
        "model": "qwen",
        "prompt": "extract_okf.md",
        "input_kinds": ["summary"],
        "output_kind": "okf_draft",
    },
    "verify_okf": {
        "enabled": True,
        "model": "qwen",
        "prompt": "verify_okf.md",
        "input_kinds": ["okf_draft"],
        "output_kind": "verified_okf",
    },
    "write_okf": {
        "enabled": True,
        "input_kinds": ["verified_okf"],
        "output_kind": "written_okf",
    },
}

STATE_MACHINE = {
    "start_kind": "source_file",
    "done_kind": "written_okf",
    "transitions": {
        "source_file": "ingest_file",
        "ingested_file": "convert_to_md",
        "markdown": "summarize",
        "summary": "extract_okf",
        "okf_draft": "verify_okf",
        "verified_okf": "write_okf",
        "written_okf": "done",
    },
}
