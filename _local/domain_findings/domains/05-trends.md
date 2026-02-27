# Domain: Trends

## Purpose

The Trends domain provides **mining industry trend analysis** via a multi-agent system. Users ask natural language questions; the system answers using knowledge graph data (~80%) and optional external market data (~20%), with source attribution and confidence scores.

## Core Behavior

1. **HTTP chat** (`POST /api/v1/trends/chat`):
   - Validates request (message length, session_id)
   - Calls `TrendsService.process_chat_message`
   - Returns `TrendsResponse` with message, intent, entities, sources, confidence scores

2. **WebSocket chat** (`WS /api/v1/trends/ws/{session_id}`):
   - Persistent connection with heartbeat (ping/pong every 30s)
   - Message types: request, status_update, response, error, ping, pong
   - Streams progress updates during analysis
   - Supports multiple queries per session

3. **Three-agent architecture**:
   - **Query planner**: Determines intent, entities, query strategy
   - **Data retrieval**: Fetches from Neo4j (KnowledgeGraphService) and optionally external APIs
   - **Supervisor**: Orchestrates agents, combines results, produces final response

4. **Configuration**: `only_use_knowledge_graph: true` skips external APIs for faster, graph-only responses

## Key Data

- **TrendsRequest**: `message`, `session_id`, `config` (e.g. only_use_knowledge_graph)
- **TrendsResponse**: `message`, `intent`, `entities_mentioned`, `sources`, `knowledge_graph_confidence`, `external_data_confidence`
- **TrendsStatusUpdate**: Streaming progress (status, agent, message, progress %)

## Boundaries

- **Depends on**: KnowledgeGraphService (Neo4j), Trends supervisor/agents (PydanticAI), optional external data
- **Depended on by**: None (leaf consumer)

## Edge Cases and Notable Logic

- **Optional auth**: `/trends/health` uses `optional_api_key` — works without key
- **Connection manager**: In-memory `TrendsConnectionManager` tracks WebSocket sessions
- **Heartbeat**: Background task pings; disconnects if send fails
- **Health check**: Validates supervisor, agents, knowledge graph availability

## What to Preserve

- Multi-agent flow (plan → retrieve → synthesize)
- Knowledge graph as primary source; external data as optional enhancement
- WebSocket streaming with progress updates
- `only_use_knowledge_graph` option for reduced latency/dependencies
