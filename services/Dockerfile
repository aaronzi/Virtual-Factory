# Image for the Virtual Factory Python services (provisioner now; data bridge, MES and ops gateway in M4).
# The repository is mounted read-only at /repo at runtime (asset data, templates, FMI model descriptions, 3D files).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_FROZEN=1 VF_REPO=/repo
COPY pyproject.toml uv.lock ./
COPY services ./services
RUN uv sync --no-dev
ENTRYPOINT ["uv", "run", "--no-sync"]
