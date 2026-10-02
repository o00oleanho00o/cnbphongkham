"""The shared object graph of one process: stores, policy, tools, engine, scheduler (package G, no TS source).

``build_runtime`` creates every real object ONCE per process and connects them the way the packages expect.
It serves both processes, with the database role of the process:

* the API (role ``be_app``): webhooks, staff routes, the CRM runner;
* the worker (role ``agent_worker``, no privilege on ``clinic.*``): turns, scheduler, KB ingest.

The cycle engine -> tool registry -> scheduler port -> scheduler deps -> engine is cut by ``LazyEngine``: the
scheduler deps are built first with a stand-in that forwards to the real engine once it exists.

Nothing here decides a business rule; the wiring only follows CONTRACTS-AI01 section 4 (how a message
travels) and the policy hook call sites of section 3.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from redis.asyncio import Redis

from pema.agent.agent_loop import AgentEngineDeps, DefaultAgentEngine, ModelResolver
from pema.agent.history_to_model_messages import StoredImage as EngineStoredImage
from pema.agent.llm_provider import resolve_language_model
from pema.agent.text_generator import ProviderTextGenerator
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.agent.tools.tool_registry import DefaultToolRegistry
from pema.agent.tools.wrap_untrusted_content import wrap_untrusted_content
from pema.channels.registry import InMemoryChannelRegistry
from pema.clinic.actions.agent_facing import ClinicAgentFacingActions
from pema.composition.adapters import (
    KbAvailabilitySnapshot,
    MarkdownStyler,
    MediaImages,
    RateLimitedSendQueue,
    ReplyCleaner,
    ScheduleParserAdapter,
    SchedulerOutboundPipeline,
    SnapshotRuntimeSettingsKv,
    VisionSidecarAdapter,
    describe_image_bytes,
    download_for_media_store,
    video_api_for,
)
from pema.config.account_store import AccountStoreImpl
from pema.config.agent_store import AgentStoreImpl
from pema.config.env import Settings
from pema.config.runtime_settings_kv import install_runtime_settings_kv
from pema.config.runtime_settings_store import (
    RuntimeSettingsSnapshot,
    SqlRuntimeSettingsStore,
    install_runtime_settings,
)
from pema.config.runtime_tuning_settings import install_tuning_provider
from pema.config.runtime_vision_settings import get_vision_settings, is_sidecar_configured
from pema.conversation.media_store import ImageDownloader, MediaStore
from pema.conversation.store import PostgresConversationStore
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.knowledge.embedding_client import EmbeddingSettings, OllamaEmbeddingClient
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore
from pema.live.publisher import install_live_publisher, installed_live_publisher
from pema.live.services import LiveServices, build_redis_live_services
from pema.mcp.mcp_agent_binding import McpBindingCache, PgMcpPolicyStore
from pema.mcp.mcp_manager import DefaultMcpManager
from pema.mcp.mcp_server_store import PgMcpServerStore
from pema.mcp.mcp_tool_provider import mcp_tool_provider
from pema.middleware.message_batcher import StorePendingInbox
from pema.middleware.redis_backends import RedisPendingBatchStore, RedisThreadRunChain, RedisTurnQueue
from pema.middleware.redis_ops import AsyncRedisOps, make_redis_client
from pema.middleware.thread_run_chain import ClinicThreadLock
from pema.policy.gateway import SqlPolicyGateway
from pema.policy.hooks import ClinicPolicyHooks
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.redis_locks import RedisLockBackend
from pema.scheduler.store import PgSchedulerStore
from pema.shared.download_image import download_image_as_base64
from pema.workers.scheduler_worker import build_send_gate
from pema_contracts.agent_turn import AgentEngine, AgentTurnRequest, AgentTurnResult, TurnCallbacks
from pema_contracts.installation import installation_clinic_id
from pema_contracts.knowledge import EmbeddingClient


class ProcessRole(StrEnum):
    API = "api"
    WORKER = "worker"


class LazyEngine:
    """``AgentEngine`` that forwards to the real engine once ``target`` is set (cuts a construction cycle)."""

    def __init__(self) -> None:
        self.target: AgentEngine | None = None

    async def run_turn(
        self, request: AgentTurnRequest, callbacks: TurnCallbacks | None = None
    ) -> AgentTurnResult:
        if self.target is None:
            raise RuntimeError("the agent engine is not wired yet")
        return await self.target.run_turn(request, callbacks)


@dataclass
class McpWiring:
    servers: PgMcpServerStore
    bindings: PgMcpPolicyStore
    cache: McpBindingCache
    manager: DefaultMcpManager


@dataclass
class Runtime:
    settings: Settings
    role: ProcessRole
    db: ClinicDatabase
    redis_client: Redis
    ops: AsyncRedisOps
    chain: RedisThreadRunChain
    turn_queue: RedisTurnQueue
    pending_store: RedisPendingBatchStore
    pending_inbox: StorePendingInbox
    thread_lock: ClinicThreadLock
    channels: InMemoryChannelRegistry
    agents: AgentStoreImpl
    accounts: AccountStoreImpl
    media: MediaStore
    media_images: MediaImages
    conversation: PostgresConversationStore
    clinic_actions: ClinicAgentFacingActions
    hooks: ClinicPolicyHooks
    knowledge: PostgresKnowledgeStore
    kb_availability: KbAvailabilitySnapshot
    mcp: McpWiring
    tool_deps: ToolDeps
    tool_registry: DefaultToolRegistry
    engine: DefaultAgentEngine
    scheduler_deps: SchedulerDeps
    scheduler: PgSchedulerStore
    snapshot: RuntimeSettingsSnapshot
    lock_backend: RedisLockBackend
    live: LiveServices
    """Live events and presence (ST-R): the publisher works in both processes, hub and presence the API."""

    async def clinic_id(self) -> UUID:
        """The id of the one clinic of this installation (read once, then cached)."""
        return await get_installation_clinic_id(self.db)

    async def close(self) -> None:
        await self.kb_availability.stop()
        if installed_live_publisher() is self.live.publisher:
            install_live_publisher(None)
        await self.live.aclose()
        await self.snapshot.stop_refresh_loop()
        await self.ops.aclose()
        await self.redis_client.aclose()
        await self.db.dispose()


def _embedder_from_env() -> EmbeddingClient | None:
    config = EmbeddingSettings()
    return OllamaEmbeddingClient(config) if config.enabled else None


async def _download_for_engine(url: str) -> EngineStoredImage | None:
    image = await download_image_as_base64(url)
    return None if image is None else EngineStoredImage(image.base64, image.media_type)


def build_runtime(
    settings: Settings,
    role: ProcessRole,
    *,
    db: ClinicDatabase | None = None,
    redis_url: str | None = None,
    resolve_model: ModelResolver | None = None,
    embedder: EmbeddingClient | Literal["env"] | None = "env",
    image_downloader: ImageDownloader | None = None,
    install_globals: bool = True,
) -> Runtime:
    """Build the graph. ``db`` / ``redis_url`` / ``resolve_model`` / ``embedder`` are for the integration
    tests (a database of their own, a fake model, no embedding service); production passes none."""
    database = db or ClinicDatabase(
        settings.database_url if role is ProcessRole.API else settings.worker_database_url
    )
    redis_client: Redis = make_redis_client(redis_url or settings.redis_url)
    ops = AsyncRedisOps(redis_client)
    chain = RedisThreadRunChain(ops)
    turn_queue = RedisTurnQueue(ops, chain)
    pending_store = RedisPendingBatchStore(ops)
    channels = InMemoryChannelRegistry()

    snapshot = RuntimeSettingsSnapshot(SqlRuntimeSettingsStore(database))
    if install_globals:
        install_runtime_settings(snapshot)
        install_tuning_provider(snapshot)
        install_runtime_settings_kv(SnapshotRuntimeSettingsKv(snapshot))

    model_resolver: ModelResolver = resolve_model or resolve_language_model
    agents = AgentStoreImpl(database)
    accounts = AccountStoreImpl(database, agents)
    media = MediaStore(
        downloader=image_downloader or download_for_media_store, describe_image=describe_image_bytes
    )
    media_images = MediaImages(media)
    conversation = PostgresConversationStore(
        database, media, ProviderTextGenerator(resolve_model=model_resolver)
    )
    clinic_actions = ClinicAgentFacingActions(database)
    hooks = ClinicPolicyHooks(actions=clinic_actions, gateway=SqlPolicyGateway(database))

    knowledge = PostgresKnowledgeStore(
        database,
        embedder=_embedder_from_env() if embedder == "env" else embedder,
        data_dir=settings.data_dir,
    )
    kb_availability = KbAvailabilitySnapshot(knowledge)

    mcp_cache = McpBindingCache()
    mcp_servers = PgMcpServerStore(database)
    mcp_bindings = PgMcpPolicyStore(database, agent_store=agents, binding_cache=mcp_cache)
    mcp_manager = DefaultMcpManager(
        server_store=mcp_servers,
        binding_store=mcp_bindings,
        bindings=mcp_cache,
        wrap=wrap_untrusted_content,
        fail=ket_qua_loi,
    )

    lazy_engine = LazyEngine()
    lock_backend = RedisLockBackend(redis_client)
    thread_lock = ClinicThreadLock(chain)
    scheduler_deps = SchedulerDeps(
        db=database,
        channels=channels,
        accounts=accounts,
        agents=agents,
        history=conversation,
        usage=conversation,
        engine=lazy_engine,
        outbound=SchedulerOutboundPipeline(),
        thread_lock=thread_lock,
        clinic_actions=clinic_actions,
        wrap_untrusted=wrap_untrusted_content,
        hooks=hooks,
        send_gate=build_send_gate(lock_backend),
    )
    scheduler = PgSchedulerStore(scheduler_deps)

    sidecar_configured: Callable[[], bool] = lambda: is_sidecar_configured(get_vision_settings())  # noqa: E731
    tool_deps = ToolDeps(
        history=conversation,
        memory=conversation,
        memory_edit=conversation.memory_edits,
        scheduler=scheduler,
        job_updater=scheduler,
        schedule_parser=ScheduleParserAdapter(),
        knowledge=knowledge,
        kb_availability=kb_availability,
        send_queue=RateLimitedSendQueue(),
        reply_cleaner=ReplyCleaner(),
        markdown_styler=MarkdownStyler(),
        stored_images=media_images,
        vision=VisionSidecarAdapter(),
        sidecar_configured=sidecar_configured,
        policy=hooks,
        clinic_actions=clinic_actions,
        video_api_for=video_api_for,
    )
    tool_registry = DefaultToolRegistry(tool_deps, mcp_provider=mcp_tool_provider)
    engine = DefaultAgentEngine(
        AgentEngineDeps(
            accounts=accounts,
            agents=agents,
            conversation=conversation,
            image_descriptions=conversation,
            tools=tool_registry,
            channels=channels,
            load_image=media_images.load_sync,
            download_image=_download_for_engine,
            policy=hooks,
            resolve_model=model_resolver,
        )
    )
    lazy_engine.target = engine

    live = build_redis_live_services(redis_client, installation_clinic_id)
    if install_globals:
        install_live_publisher(live.publisher)

    return Runtime(
        settings=settings,
        role=role,
        db=database,
        redis_client=redis_client,
        ops=ops,
        chain=chain,
        turn_queue=turn_queue,
        pending_store=pending_store,
        pending_inbox=StorePendingInbox(pending_store),
        thread_lock=thread_lock,
        channels=channels,
        agents=agents,
        accounts=accounts,
        media=media,
        media_images=media_images,
        conversation=conversation,
        clinic_actions=clinic_actions,
        hooks=hooks,
        knowledge=knowledge,
        kb_availability=kb_availability,
        mcp=McpWiring(mcp_servers, mcp_bindings, mcp_cache, mcp_manager),
        tool_deps=tool_deps,
        tool_registry=tool_registry,
        engine=engine,
        scheduler_deps=scheduler_deps,
        scheduler=scheduler,
        snapshot=snapshot,
        lock_backend=lock_backend,
        live=live,
    )
