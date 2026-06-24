FROM oven/bun:1.3.14 AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

FROM base AS builder

WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
RUN bun run build

FROM base AS runner

WORKDIR /app

ENV HOST=0.0.0.0
ENV NODE_ENV=production
ENV PORT=3000

COPY --from=builder /app/.output ./.output

EXPOSE 3000

CMD ["bun", ".output/server/index.mjs"]
