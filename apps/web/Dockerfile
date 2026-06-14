FROM node:22-alpine AS base
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --filter @courtvision/web... --frozen-lockfile=false
COPY apps/web apps/web
WORKDIR /app/apps/web
RUN pnpm build
CMD ["pnpm", "start"]
