"""Core structures and small builders for benzaiten.

This file defines the shapes of the system:
- physical hosts
- compute nodes
- models
- agents

It should not contain concrete project instances such as PC1, Qwen, or Gemma.
Those belong in config.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


# =====================================================================
# 1. STANDARDISED TYPE DEFINITIONS
# =====================================================================

DeviceType = Literal["cpu", "gpu"]
AccessType = Literal["local", "ssh"]
MemoryType = Literal["system_ram", "vram"]

ModelRole = Literal["agent", "coder", "summarizer", "reasoning", "reviewer"]
AgentRole = Literal["orchestrator", "state_machine", "agent", "operator", "reviewer", "reasoning_worker"]

ModelInterfaceType = Literal["openai_compatible_api", "cli"]
AgentInterfaceType = Literal["python_subprocess", "anythingllm_api"]


# =====================================================================
# 2. CORE COMPONENT STRUCTS
# =====================================================================

@dataclass(frozen=True)
class MemoryStruct:
    """Configured memory capacity for a compute node."""

    total_gb: float
    reserved_system_gb: float
    memory_type: MemoryType

    @property
    def available_memory_gb(self) -> float:
        """Configured usable memory after static reservation."""
        return self.total_gb - self.reserved_system_gb


@dataclass(frozen=True)
class HostStruct:
    """Physical PC / connection boundary."""

    phys_host: str
    system_hostname: str
    address_local: str
    address_external: Optional[str]
    access_type: AccessType
    shared_root: Path
    ssh_port: Optional[int]
    ssh_user: Optional[str]
    ssh_key_env: Optional[str]


@dataclass(frozen=True)
class ComputeNodeStruct:
    """Single compute unit inside a host, e.g. pc1.cpu or pc1.gpu0."""

    node: str
    phys_host: str
    device_type: DeviceType
    device_id: Optional[int]
    device_name: str
    memory: Optional[MemoryStruct]


@dataclass(frozen=True)
class ModelStruct:
    """Static model deployment attached to one compute node."""

    model_name: str
    node: str
    interface_type: ModelInterfaceType

    # Endpoint interface fields
    endpoint_url: Optional[str]
    endpoint_port: Optional[int]
    api_key_env: Optional[str]

    # CLI interface fields
    cli_command: Optional[str]
    working_dir: Optional[Path]

    # Routing hints
    role: list[ModelRole]

    # Model limits
    context_tokens: int
    output_tokens: int
    temperature: float


@dataclass(frozen=True)
class AgentStruct:
    """Active runtime/process attached to one compute node."""

    name: str
    node: str
    interface_type: AgentInterfaceType
    role: list[AgentRole]
    uses_model: Optional[str]  # key in MODELS, e.g. "qwen"

    # Agent/tool limits
    max_tool_calls_per_task: int
    max_file_read_lines: int
    session_isolation: bool


# =====================================================================
# 3. PROGRAMMATIC ELEMENT BUILDERS
# =====================================================================

def make_memory(
    *,
    total_gb: float,
    reserved_system_gb: float,
    memory_type: MemoryType,
) -> MemoryStruct:
    """Create configured memory metadata and reject impossible reservations."""

    if total_gb <= 0:
        raise ValueError("total_gb must be positive.")

    if reserved_system_gb < 0:
        raise ValueError("reserved_system_gb cannot be negative.")

    if reserved_system_gb > total_gb:
        raise ValueError("reserved_system_gb cannot exceed total_gb.")

    return MemoryStruct(
        total_gb=total_gb,
        reserved_system_gb=reserved_system_gb,
        memory_type=memory_type,
    )


def make_compute_node(
    *,
    phys_host: str,
    device_type: DeviceType,
    device_id: Optional[int],
    device_name: str,
    memory: Optional[MemoryStruct],
) -> ComputeNodeStruct:
    """Assemble one compute node and generate its unique identity string."""

    if device_type == "cpu":
        if device_id is not None:
            raise ValueError("CPU node must use device_id=None.")
        node_identity = f"{phys_host}.cpu"
        final_device_id = None

    elif device_type == "gpu":
        if device_id is None:
            raise ValueError("GPU node requires device_id, e.g. 0 or 1.")
        if device_id < 0:
            raise ValueError("GPU device_id cannot be negative.")
        node_identity = f"{phys_host}.gpu{device_id}"
        final_device_id = device_id

    else:
        raise ValueError(f"Unsupported device_type: {device_type}")

    return ComputeNodeStruct(
        node=node_identity,
        phys_host=phys_host,
        device_type=device_type,
        device_id=final_device_id,
        device_name=device_name,
        memory=memory,
    )


# =====================================================================
# 4. RUNTIME MEMORY CHECK PLACEHOLDERS
# =====================================================================


def get_runtime_available_memory_gb(node: ComputeNodeStruct) -> float:
    """Return live available memory for a compute node.

    Later implementation:
    - CPU/system_ram: psutil.virtual_memory().available
    - GPU/vram: nvidia-smi or pynvml
    """

    raise NotImplementedError("Runtime memory probing is not implemented yet.")


def has_enough_runtime_memory(
    *,
    node: ComputeNodeStruct,
    required_gb: float,
) -> bool:
    """Check whether a compute node currently has enough live memory."""

    return get_runtime_available_memory_gb(node) >= required_gb
