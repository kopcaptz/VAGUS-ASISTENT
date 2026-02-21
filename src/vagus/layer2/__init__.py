"""
Слой 2: Агентная система — Orchestrator-Worker.
"""

from typing import Any, Optional

from .communication import (
    CommunicationLayer,
    SharedBlackboard,
    create_communication_from_config,
)
from .communication.blackboard import create_blackboard_from_config
from .agent_registry import AgentRegistry
from .agents.base_agent import BaseAgent
from .agents.analyst import AnalystAgent
from .agents.coder import CoderAgent
from .agents.designer_agent import DesignerAgent
from .agents.evaluator import EvaluatorAgent
from .agents.reflection import ReflectionAgent
from .agents.researcher import ResearcherAgent
from .dead_letter_queue import DeadLetterQueueStorage
from .intent_classifier import IntentClassifier, IntentResult, create_intent_classifier
from .memory import (
    ConversationSummarizer,
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    intent_to_summary,
)
from .planning import TaskPlan, TaskPlanner, TaskStep, create_task_planner, task_plan_get_ordered_steps, task_plan_to_multi_steps
from .orchestrator import MasterOrchestrator, TaskOrchestrator
from .skills import SkillSystem


def create_conversation_summarizer_from_config(
    llm_router: Any,
    layer2_config: Optional[dict[str, Any]],
) -> ConversationSummarizer:
    """Создаёт ConversationSummarizer из layer2.conversation_summarizer."""
    cfg = (layer2_config or {}).get("conversation_summarizer") or {}
    if not isinstance(cfg, dict):
        return ConversationSummarizer(llm_router, enabled=False)
    enabled = cfg.get("enabled", True)
    max_input_steps = int(cfg.get("max_input_steps", 50))
    min_summary_words = int(cfg.get("min_summary_words", 50))
    max_summary_words = int(cfg.get("max_summary_words", 500))
    return ConversationSummarizer(
        llm_router,
        enabled=enabled,
        max_input_steps=max_input_steps,
        min_summary_words=min_summary_words,
        max_summary_words=max_summary_words,
    )


def create_procedural_memory_from_config(
    layer2_config: Optional[dict[str, Any]],
) -> ProceduralMemory:
    """Создаёт ProceduralMemory из layer2.procedural_memory."""
    cfg = (layer2_config or {}).get("procedural_memory") or {}
    if not isinstance(cfg, dict):
        return ProceduralMemory(enabled=False)
    enabled = cfg.get("enabled", True)
    db_path = cfg.get("db_path", "data/procedural.db")
    return ProceduralMemory(db_path=str(db_path), enabled=enabled)


def create_orchestrator_with_researcher(
    llm_router: Any,
    *,
    dead_letter_queue: Optional[DeadLetterQueueStorage] = None,
    task_timeouts: Optional[dict[str, float]] = None,
    cluster_config: Optional[dict[str, Any]] = None,
) -> TaskOrchestrator:
    """
    Создаёт TaskOrchestrator с зарегистрированным ResearcherAgent.
    Удобная точка входа для E2E и первого сценария.
    """
    communication = CommunicationLayer()
    skill_system = SkillSystem()
    researcher = ResearcherAgent(llm_router=llm_router, skill_system=skill_system)
    orchestrator = TaskOrchestrator(
        communication=communication,
        dead_letter_queue=dead_letter_queue,
        task_timeouts=task_timeouts,
        skill_system=skill_system,
        cluster_config=cluster_config,
    )
    orchestrator.register_agent(researcher)
    return orchestrator


def create_master_orchestrator_full(
    llm_router: Any,
    *,
    layer2_config: Optional[dict[str, Any]] = None,
) -> MasterOrchestrator:
    """
    Создаёт MasterOrchestrator с IntentClassifier, TaskPlanner, SharedBlackboard
    и всеми агентами (Researcher, Coder, Analyst, Designer).
    """
    layer2 = layer2_config or {}
    intent_classifier = create_intent_classifier(llm_router, layer2.get("intent_classifier"))
    procedural_memory = create_procedural_memory_from_config(layer2)
    proc_cfg = (layer2.get("procedural_memory") or {}) if isinstance(layer2.get("procedural_memory"), dict) else {}
    similarity_threshold = float(proc_cfg.get("similarity_threshold", 0.7))
    task_planner = create_task_planner(
        llm_router,
        layer2.get("task_planner"),
        procedural_memory=procedural_memory,
        similarity_threshold=similarity_threshold,
    )
    shared_blackboard = create_blackboard_from_config(layer2)
    event_bus = create_communication_from_config(layer2)
    conversation_summarizer = create_conversation_summarizer_from_config(llm_router, layer2)
    from .memory import (
        CoherenceMonitor,
        MemoryConsolidationHandler,
        MemoryManager,
        SynapticTrainingHandler,
        create_artifact_kb_from_config,
    )

    artifact_kb = create_artifact_kb_from_config(layer2)
    memory_manager = MemoryManager(
        procedural_memory=procedural_memory,
        artifact_kb=artifact_kb,
    )
    coherence_monitor = CoherenceMonitor(
        summarizer=conversation_summarizer,
        threshold_steps=int((layer2.get("coherence") or {}).get("threshold_steps", 10)),
    )
    memory_consolidation_handler = MemoryConsolidationHandler(
        episodic_memory=memory_manager.episodic,
        semantic_memory=memory_manager.semantic,
        procedural_memory=procedural_memory,
    )
    synaptic_handler = SynapticTrainingHandler(artifact_kb=artifact_kb)
    skill_system = SkillSystem()
    from ..plugins import PluginManager

    agents = [
        ResearcherAgent(llm_router=llm_router, skill_system=skill_system),
        CoderAgent(llm_router=llm_router, skill_system=skill_system),
        AnalystAgent(llm_router=llm_router),
        EvaluatorAgent(llm_router=llm_router),
        ReflectionAgent(llm_router=llm_router),
        DesignerAgent(llm_router=llm_router, plugin_manager=PluginManager()),
    ]
    agent_registry = AgentRegistry(agents)
    return MasterOrchestrator(
        llm_router=llm_router,
        intent_classifier=intent_classifier,
        task_planner=task_planner,
        shared_blackboard=shared_blackboard,
        agent_registry=agent_registry,
        event_bus=event_bus,
        procedural_memory=procedural_memory,
        conversation_summarizer=conversation_summarizer,
        memory_manager=memory_manager,
        coherence_monitor=coherence_monitor,
        memory_consolidation_handler=memory_consolidation_handler,
        synaptic_handler=synaptic_handler,
        config=layer2.get("master_orchestrator"),
    )


def create_orchestrator_full(
    llm_router: Any,
    *,
    dead_letter_queue: Optional[DeadLetterQueueStorage] = None,
    task_timeouts: Optional[dict[str, float]] = None,
    error_analytics: Optional[Any] = None,
    cluster_config: Optional[dict[str, Any]] = None,
    enable_reflexion: bool = True,
    max_reflection_iterations: int = 2,
    reflection_threshold: float = 0.7,
    orchestrator_type: str = "task",
    layer2_config: Optional[dict[str, Any]] = None,
) -> TaskOrchestrator | MasterOrchestrator:
    """
    Создаёт оркестратор. orchestrator_type: "task" (TaskOrchestrator) или "master" (MasterOrchestrator).
    """
    if orchestrator_type == "master":
        return create_master_orchestrator_full(llm_router, layer2_config=layer2_config)

    communication = CommunicationLayer()
    memory = EpisodicMemory()
    semantic_memory = SemanticMemory()
    skill_system = SkillSystem()
    from ..plugins import PluginManager

    orchestrator = TaskOrchestrator(
        communication=communication,
        memory=memory,
        semantic_memory=semantic_memory,
        dead_letter_queue=dead_letter_queue,
        task_timeouts=task_timeouts,
        skill_system=skill_system,
        error_analytics=error_analytics,
        cluster_config=cluster_config,
        enable_reflexion=enable_reflexion,
        max_reflection_iterations=max_reflection_iterations,
        reflection_threshold=reflection_threshold,
    )
    orchestrator.register_agent(ResearcherAgent(llm_router=llm_router, skill_system=skill_system))
    orchestrator.register_agent(CoderAgent(llm_router=llm_router, skill_system=skill_system))
    orchestrator.register_agent(AnalystAgent(llm_router=llm_router))
    orchestrator.register_agent(EvaluatorAgent(llm_router=llm_router))
    orchestrator.register_agent(ReflectionAgent(llm_router=llm_router))
    orchestrator.register_agent(
        DesignerAgent(
            llm_router=llm_router,
            plugin_manager=PluginManager(),
        )
    )
    return orchestrator


__all__ = [
    "ConversationSummarizer",
    "create_communication_from_config",
    "create_conversation_summarizer_from_config",
    "create_procedural_memory_from_config",
    "AnalystAgent",
    "AgentRegistry",
    "MasterOrchestrator",
    "CommunicationLayer",
    "SharedBlackboard",
    "BaseAgent",
    "IntentClassifier",
    "IntentResult",
    "CoderAgent",
    "DeadLetterQueueStorage",
    "DesignerAgent",
    "EvaluatorAgent",
    "ReflectionAgent",
    "EpisodicMemory",
    "ProceduralMemory",
    "ResearcherAgent",
    "SemanticMemory",
    "TaskPlan",
    "TaskPlanner",
    "TaskStep",
    "create_task_planner",
    "create_master_orchestrator_full",
    "task_plan_get_ordered_steps",
    "task_plan_to_multi_steps",
    "TaskOrchestrator",
    "SkillSystem",
    "create_orchestrator_full",
    "create_orchestrator_with_researcher",
]
