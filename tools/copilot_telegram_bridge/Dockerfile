FROM python:3.12-slim

LABEL maintainer="taris/sintaris-openclaw"
LABEL description="Copilot Telegram MCP Bridge — notifications and approvals via Telegram"

# mcp pulls in uvicorn+starlette via sse-starlette which is needed for SSE transport
RUN pip install --no-cache-dir "mcp>=1.0.0,<2.0.0"

WORKDIR /app

COPY scripts/telegram_bridge.py .
COPY scripts/mcp_server.py .

ENV PYTHONUNBUFFERED=1
# SSE transport — VS Code connects via SSH tunnel to localhost:3001/sse
ENV MCP_TRANSPORT=sse
ENV MCP_HOST=127.0.0.1
ENV MCP_PORT=3001

EXPOSE 3001

CMD ["python", "mcp_server.py"]
