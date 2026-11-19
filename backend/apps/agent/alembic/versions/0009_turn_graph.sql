-- A turn may run along a plugin's graph (docs/PLAN-rag-graph.md 4): its trace gets one event per node ("node") and
-- a turn whose walk ran out of nodes stops with "graph".
ALTER TABLE agent_rt.agent_turn
    DROP CONSTRAINT agent_turn_stop,
    ADD CONSTRAINT agent_turn_stop CHECK (
        stop = ANY (ARRAY['completed', 'max_steps', 'deadline', 'budget', 'loop', 'graph', 'error'])
    );

ALTER TABLE agent_rt.agent_turn_event
    DROP CONSTRAINT agent_turn_event_kind,
    ADD CONSTRAINT agent_turn_event_kind CHECK (
        kind = ANY (ARRAY['model_call', 'tool_call', 'compaction', 'memory_flush', 'repair', 'model_retry', 'guard',
                          'inbox', 'node'])
    );
